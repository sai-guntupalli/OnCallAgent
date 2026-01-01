from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any

from .agent.core import run_agent
from .agent.prompts import format_incident_report
from .database import db

app = FastAPI(title="OnCall Agent API", version="1.0")

@app.on_event("startup")
async def startup_event():
    from .agent.core import config
    print(f"🚀 OnCall Agent API Starting...")
    print(f"🤖 Active Model: {config.agent.model}")

class IncidentRequest(BaseModel):
    source_system: str  # e.g. "airflow", "databricks"
    incident_id: str
    title: str
    description: str
    logs: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}

@app.post("/analyze")
async def analyze_incident(incident: IncidentRequest, background_tasks: BackgroundTasks):
    """
    Endpoint to trigger the agent analysis for a reported incident.
    Analysis runs in background to avoid blocking the caller (Airflow).
    """
    try:
        # Construct the user prompt from the structured request
        prompt = format_incident_report(
            source_system=incident.source_system,
            incident_id=incident.incident_id,
            title=incident.title,
            description=incident.description,
            logs=incident.logs,
            metadata=incident.metadata or {}
        )
        
        # Log reception
        db.log_action("API_REQUEST_RECEIVED", incident.model_dump())
        
        # Trigger Agent (in background for async processing)
        # In a real production app, this would push to a queue (Redis/Celery).
        background_tasks.add_task(run_agent_task, prompt)
        
        return {"status": "accepted", "message": "Incident queued for analysis."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def run_agent_task(prompt: str):
    """Helper to run agent asynchronously in background task."""
    print(f"Starting analysis for prompt: {prompt[:50]}...")
    await run_agent(prompt)
