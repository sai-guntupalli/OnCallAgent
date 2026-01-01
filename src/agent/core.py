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


