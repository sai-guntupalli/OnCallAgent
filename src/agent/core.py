from google.adk import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.models.lite_llm import LiteLlm
from google.genai import types as genai_types
from ..config import config
from ..database import db
import asyncio
import json
import uuid

# Import Tools
from .tools.airflow import get_airflow_dag_status, get_airflow_logs, retry_airflow_pipeline
from .tools.databricks import analyze_databricks_error, restart_databricks_job
from .tools.snowflake import analyze_snowflake_query_error
from .tools.tickets import create_incident_ticket, update_ticket_status

# Callback to log every step to DuckDB
def audit_log_callback(event):
    # This is a simplified view of how one might hook into the runner.
    # For this customized implementation using standard 'Agent' which might not easily expose global hooks 
    # without a Runner, we will rely on the tools themselves logging implicit actions 
    # OR wrapper logic in the 'run' method below.
    pass

SYSTEM_INSTRUCTION = """
You are a **Senior Data Engineering OnCall Agent**.
Your primary mission is to autonomously diagnose, triage, and resolve data pipeline failures across Airflow, Databricks, and Snowflake.

### 🛡️ Core Responsibilities
1.  **Diagnosis**: Analyze logs and error messages to pinpoint the root cause (e.g., Data Quality, Cluster Connectivity, SQL Syntax, Timeout).
2.  **Triage**: Classify the severity and type of error (Transient vs. Permanent).
3.  **Remediation**: Execute safe fixes (Retries) or escalate complex issues (Ticketing).
4.  **Audit**: Your reasoning and actions are logged. Be precise and professional.

### 🔬 Operational Protocol

#### Phase 1: Investigation
- **Context Gathering**: Look for DAG IDs, Run IDs, and specific Error Messages in the user input.
- **Log Analysis**:
    - If the user provides raw log text (e.g., "Error: Cluster unavailable"), treat this as `mock_logs` and pass it to tools like `analyze_databricks_error` directly.
    - If no logs are provided, use `get_airflow_logs` to fetch them from the source.

#### Phase 2: Classification
- **Transient Failures** (Retryable):
    - Network Timeouts, API rate limits, Cluster unavailable, Temporary resource contention.
    - **Action**: Use `retry_airflow_pipeline` or `restart_databricks_job`.
- **Permanent Failures** (Non-Retryable):
    - Code/Syntax errors, Missing source files, Schema mismatch, Data quality check failures.
    - **Action**: Do NOT retry. Create a ticket immediately.

#### Phase 3: Action & Escalation
- **Retrying**: Only retry ONCE. If a task has already been retried (check try_number), do not retry again loop infinitely.
- **Ticketing**: When creating a ticket (`create_incident_ticket`), provide:
    - **Title**: formatted as `[<System>] <ErrorType> in <PipelineName>`
    - **Description**: Include the Root Cause, relevant Log Snippets, and your analysis of why it failed.
    - **Priority**: Set 'Critical' for SLA breaches, 'Medium' for nightly loads.

### ⚠️ Guardrails & Safety
- **NO DESTRUCTIVE ACTIONS**: Do not delete tables, drop schemas, or cancel running jobs unless explicitly instructed.
- **Mock Mode Reliability**: If you cannot connect to a real API (e.g., Airflow unreachable), admit it and ask the user if they have `mock_logs` to provide. Do not hallucinate successful API calls.

### 🗣️ Trace of Thought
Before taking any tool action, briefly explain your reasoning:
"I see a timeout error in the finance_dag. This looks transient. I will check the current status and then attempt a retry."
"""

def create_agent() -> Agent:
    model_name = config.agent.model
    
    # Use LiteLlm for non-Gemini models (OpenAI, Claude, etc.)
    # Native ADK 'Agent' expects a model object or a recognized string for Gemini.
    if "gemini" in model_name.lower():
        llm_model = model_name
    else:
        # For OpenAI, LiteLLM usually wants a prefix or the clean model name
        # We'll use LiteLlm wrapper which handles the routing
        llm_model = LiteLlm(model=model_name)

    return Agent(
        name=config.agent.name,
        model=llm_model,
        instruction=SYSTEM_INSTRUCTION,
        tools=[
            get_airflow_dag_status, 
            get_airflow_logs, 
            retry_airflow_pipeline,
            analyze_databricks_error, 
            restart_databricks_job,
            analyze_snowflake_query_error,
            create_incident_ticket, 
            update_ticket_status
        ]
    )


async def run_agent(user_input: str):
    """
    Entry point to run the agent for a single turn. 
    Uses ADK Runner to handle multi-step reasoning and tool calls.
    Returns the final response text.
    """
    agent = create_agent()
    
    # Initialize session service and runner
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent, 
        session_service=session_service,
        app_name=config.agent.name
    )
    
    # Create a unique session for this turn
    user_id = "default_user"
    session_id = str(uuid.uuid4())
    await session_service.create_session(
        app_name=config.agent.name,
        user_id=user_id,
        session_id=session_id
    )
    
    # Log Start
    db.log_action("AGENT_START", {"input": user_input})
    
    try:
        print(f"🤖 Agent ({config.agent.name}) starting analysis...")
        
        # Prepare the input content
        new_message = genai_types.Content(
            role="user",
            parts=[genai_types.Part.from_text(text=user_input)]
        )
        
        final_text = ""
        # The runner.run_async in this ADK version is an async generator of events
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_message
        ):
            # We look for the final response event or any content parts emitted
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        final_text = part.text
        
        # Log Success
        db.log_action("AGENT_SUCCESS", {
            "response": final_text,
            "session_id": session_id
        })
        
        print(f"\n✅ Agent Response:\n{final_text}")
        return final_text
        
    except Exception as e:
        error_msg = str(e)
        import traceback
        traceback.print_exc()
        db.log_action("AGENT_ERROR", {"error": error_msg})
        print(f"❌ Agent Error: {error_msg}")
        return f"Error occurred during analysis: {error_msg}"

