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

# Import Prompts
from .prompts import SYSTEM_INSTRUCTION

# Callback to log every step to DuckDB
def audit_log_callback(event):
    # This is a simplified view of how one might hook into the runner.
    # For this customized implementation using standard 'Agent' which might not easily expose global hooks 
    # without a Runner, we will rely on the tools themselves logging implicit actions 
    # OR wrapper logic in the 'run' method below.
    pass



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

def smart_trim_logs(logs: str) -> str:
    """ Extract critical lines (Error, Exception, Traceback) from logs to save tokens. """
    if not config.agent.smart_log_trimming:
        return logs
        
    lines = logs.split("\n")
    critical_lines = []
    
    # Heuristic: keep lines with 'Error', 'Exception', 'Trace', or specific codes
    keywords = ["error", "exception", "traceback", "failed", "exit code", "fatal"]
    for i, line in enumerate(lines):
        if any(key in line.lower() for key in keywords):
            # Include content and a bit of context around it
            start = max(0, i-2)
            end = min(len(lines), i+3)
            critical_lines.extend(lines[start:end])
            
    if not critical_lines:
        return logs[:2000] # Fallback to head if no keywords found
        
    return "\n".join(list(dict.fromkeys(critical_lines))) # Deduplicate while preserving order

async def run_agent(user_input: str, incident_id: str):
    """
    Entry point to run the agent.
    Uses LangGraph to handle multi-step reasoning and tool calls.
    """
    agent = create_agent()
    
    # Log Start
    db.log_action("AGENT_START", {"input": user_input}, incident_id=incident_id)
    
    try:
        print(f"🤖 Agent ({config.agent.name}) starting analysis with LangGraph [ID: {incident_id}]...")
        
        # Smart Trim log text in user input if present
        if config.agent.smart_log_trimming and "Incident Report" in user_input:
            # Simple heuristic to find logs section
            parts = user_input.split("Logs:")
            if len(parts) > 1:
                header = parts[0]
                logs_and_metadata = parts[1].split("Metadata:")
                logs = logs_and_metadata[0]
                metadata = logs_and_metadata[1] if len(logs_and_metadata) > 1 else ""
                
                trimmed_logs = smart_trim_logs(logs)
                user_input = f"{header}Logs: (Smart Trimmed)\n{trimmed_logs}\nMetadata:{metadata}"

        inputs = {"messages": [HumanMessage(content=f"{user_input}\n\n[INTERNAL_INCIDENT_ID: {incident_id}]")]}
        config_run = {"configurable": {"thread_id": str(uuid.uuid4())}}
        
        # We need to use a stream or a turn-based loop to track tokens per turn if we want granularity.
        # But create_react_agent is a full graph. We can get usage from the final response 
        # but that's only the LAST turn's tokens. 
        # To get all turns, we can iterate over the messages in the final state.
        
        final_state = await agent.ainvoke(inputs, config=config_run)
        
        # Track usage for all AI messages in the trace
        turn_index = 0
        for msg in final_state["messages"]:
            if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                usage = msg.usage_metadata
                db.track_token_usage(
                    incident_id=incident_id,
                    model=config.agent.model,
                    prompt_tokens=usage.get("input_tokens", 0),
                    completion_tokens=usage.get("output_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    turn_index=turn_index
                )
                turn_index += 1
        
        # The final message is the last one in the 'messages' list
        final_text = final_state["messages"][-1].content
        
        # Log Success
        db.log_action("AGENT_SUCCESS", {
            "response": final_text,
            "session_id": config_run["configurable"]["thread_id"]
        }, incident_id=incident_id)
        
        print(f"\n✅ Agent Response:\n{final_text}")
        return final_text
        
    except Exception as e:
        error_msg = str(e)
        import traceback
        traceback.print_exc()
        db.log_action("AGENT_ERROR", {"error": error_msg}, incident_id=incident_id)
        print(f"❌ Agent Error: {error_msg}")
        return f"Error occurred during analysis: {error_msg}"


