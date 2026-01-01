from typing import List, Union
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage, HumanMessage
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
    - **Resolution Guide**: Provide a step-by-step guide on how to resolve the issue based on the data you have. These steps should help the OnCall Engineer to resolve the issue as quickly as possible. If you dont have enough data, dont provide wrong or incomplete steps.
    - **Priority**: Set 'Critical' for SLA breaches, 'Medium' for nightly loads.

### ⚠️ Guardrails & Safety
- **NO DESTRUCTIVE ACTIONS**: Do not delete tables, drop schemas, or cancel running jobs unless explicitly instructed.
- **Mock Mode Reliability**: If you cannot connect to a real API (e.g., Airflow unreachable), admit it and ask the user if they have `mock_logs` to provide. Do not hallucinate successful API calls.

### 🗣️ Trace of Thought
Before taking any tool action, briefly explain your reasoning:
"I see a timeout error in the finance_dag. This looks transient. I will check the current status and then attempt a retry."

Always respond to the user, even if just to acknowledge receipt of the incident, before calling tools.
"""

def get_model():
    model_name = config.agent.model
    api_key = config.llm_key
    
    # Debug logging to identify the actual path taken
    print(f"!!! DEBUG RUNTIME !!! Model Name: '{model_name}'")
    print(f"!!! DEBUG RUNTIME !!! API Key Present: {bool(api_key)}")
    
    if "gemini" in model_name.lower():
        print("!!! DEBUG !!! Using GOOGLE GENAI PROVIDER")
        return ChatGoogleGenerativeAI(
            model=model_name, 
            google_api_key=api_key, 
            temperature=0.1,
            max_retries=3,
            safety_settings={
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            }
        )
    else:
        print(f"!!! DEBUG !!! Using OPENAI PROVIDER with model {model_name}")
        return ChatOpenAI(
            model=model_name, 
            openai_api_key=api_key, 
            temperature=0.1,
            max_retries=3
        )

def create_agent():
    llm = get_model()
    tools = [
        get_airflow_dag_status, 
        get_airflow_logs, 
        retry_airflow_pipeline,
        analyze_databricks_error, 
        restart_databricks_job,
        analyze_snowflake_query_error,
        create_incident_ticket, 
        update_ticket_status
    ]
    
    # LangGraph's prebuilt ReAct agent
    # Passing prompt as a string converts it to a SystemMessage internally in create_react_agent
    agent = create_react_agent(llm, tools, prompt=SYSTEM_INSTRUCTION, debug=True)
    return agent

async def run_agent(user_input: str):
    """
    Entry point to run the agent.
    Uses LangGraph to handle multi-step reasoning and tool calls.
    """
    agent = create_agent()
    # Log the exact model type for debugging
    # In create_react_agent, the model is bound to the 'agent' node
    try:
        model_type = type(agent.get_graph().nodes['agent'].bound).__name__
        print(f"DEBUG: LangGraph Agent Model: {model_type}")
    except:
        pass
    
    # Log Start
    db.log_action("AGENT_START", {"input": user_input})
    
    try:
        print(f"🤖 Agent ({config.agent.name}) starting analysis with LangGraph...")
        
        # In LangGraph create_react_agent, the state is message-based
        inputs = {"messages": [HumanMessage(content=user_input)]}
        
        # Run the agent synchronously for this turn (getting all steps)
        # For a production app, you might want to stream events.
        config_run = {"configurable": {"thread_id": str(uuid.uuid4())}}
        
        final_state = await agent.ainvoke(inputs, config=config_run)
        
        # The final message is the last one in the 'messages' list
        final_text = final_state["messages"][-1].content
        
        # Log Success
        db.log_action("AGENT_SUCCESS", {
            "response": final_text,
            "session_id": config_run["configurable"]["thread_id"]
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


