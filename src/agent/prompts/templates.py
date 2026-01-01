import json
import textwrap
from typing import Any

def format_incident_report(source_system: str, incident_id: str, title: str, description: str, logs: str | None, metadata: dict[str, Any]) -> str:
    """Format an incident into a prompt for the agent."""
    logs_text = logs or "No logs provided. Please fetch via API."
    metadata_text = json.dumps(metadata, indent=2)
    
    return textwrap.dedent(f"""
        Incident Report from {source_system}:
        ID: {incident_id}
        Title: {title}
        Description: {description}
        Logs: {logs_text}
        Metadata: {metadata_text}
    """).strip()
