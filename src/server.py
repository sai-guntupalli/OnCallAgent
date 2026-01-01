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

import uuid

@app.post("/analyze")
async def analyze_incident(incident: IncidentRequest, background_tasks: BackgroundTasks):
    """
    Endpoint to trigger the agent analysis for a reported incident.
    Analysis runs in background to avoid blocking the caller (Airflow).
    """
    try:
        # Recover existing incident_id if present (for retries), else generate new
        internal_id = incident.metadata.get("parent_incident_id") if incident.metadata else None
        if not internal_id:
            internal_id = f"INC-{str(uuid.uuid4())[:8].upper()}"
        
        # Construct the user prompt from the structured request
        prompt = format_incident_report(
            source_system=incident.source_system,
            incident_id=incident.incident_id,
            title=incident.title,
            description=incident.description,
            logs=incident.logs,
            metadata=incident.metadata or {}
        )
        
        # Log reception with correlation ID
        db.log_action("API_REQUEST_RECEIVED", {
            "external_id": incident.incident_id,
            "source": incident.source_system,
            "title": incident.title
        }, incident_id=internal_id)
        
        # Trigger Agent (in background for async processing)
        background_tasks.add_task(run_agent_task, prompt, internal_id)
        
        return {
            "status": "accepted", 
            "message": "Incident queued for analysis.",
            "incident_id": internal_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def run_agent_task(prompt: str, incident_id: str):
    """Helper to run agent asynchronously in background task."""
    print(f"Starting analysis for incident {incident_id}...")
    await run_agent(prompt, incident_id)
