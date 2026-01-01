from typing import Optional

def analyze_databricks_error(run_id: str, mock_logs: Optional[str] = None) -> str:
    """
    Analyzes a Databricks job run error.
    
    Args:
        run_id: The Databricks job run ID.
        mock_logs: Optional string containing specific error logs to analyze (for testing/mocking).
    """
    if mock_logs:
        return f"Analyzed provided logs for Run {run_id}. \nFinding: The logs indicate a specific failure based on the provided text: '{mock_logs[:100]}...'"
    
    # Real implementation would go here (using databricks-sdk)
    return f"Real Databricks API call for run_id {run_id} is not yet implemented. Please provide mock_logs."

from ...database import db
from ...config import config

def restart_databricks_job(job_id: str, incident_id: str) -> str:
    """Restarts a Databricks job. Requires incident_id for retry tracking.
    Note: In a real implementation, incident_id should be passed as a job parameter 
    (e.g., in base_parameters) so it can be recovered on failure logs.
    """
    # Check internal retry guardrail
    current_retries = db.increment_retry_count(incident_id, job_id)
    max_allowed = config.agent.max_retries
    
    if current_retries > max_allowed:
        return f"RETRY_DENIED: You have already attempted to restart {job_id} {max_allowed} times for incident {incident_id}. DO NOT retry again. Please create a ticket instead."

    return f"Restarted Databricks job {job_id} (Attempt {current_retries}/{max_allowed}) (Mock Action)"
