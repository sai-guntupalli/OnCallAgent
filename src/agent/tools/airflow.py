import httpx
import json
from typing import Dict, Any, List, Optional, Union
from ...config import config

class AirflowClient:
    def __init__(self):
        self.base_url = config.airflow_url
        self.auth = (config.airflow_username, config.airflow_password)
        
    def _get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        url = f"{self.base_url}/api/v1/{endpoint}"
        try:
            response = httpx.get(url, auth=self.auth, params=params, timeout=10.0)
            response.raise_for_status()
            try:
                return response.json()
            except json.JSONDecodeError:
                # Fallback for plain text responses (common for Airflow logs)
                return {"content": response.text}
        except httpx.RequestError as e:
            return {"error": f"Request failed: {str(e)}"}
        except httpx.HTTPStatusError as e:
             return {"error": f"HTTP error {e.response.status_code}: {e.response.text}"}

    def get_dag_run(self, dag_id: str, dag_run_id: str) -> Dict[str, Any]:
        return self._get(f"dags/{dag_id}/dagRuns/{dag_run_id}")

    def get_task_instances(self, dag_id: str, dag_run_id: str) -> Dict[str, Any]:
        return self._get(f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances")

    def get_task_log(self, dag_id: str, dag_run_id: str, task_id: str, try_number: int = 1) -> str:
        # Note: Airflow API often returns logs in a specific format or requires following a redirect.
        # This is a simplified version getting the log content directly if available.
        res = self._get(f"dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}")
        if "content" in res:
            return res["content"]
        return str(res)

    def trigger_dag(self, dag_id: str, conf: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}/api/v1/dags/{dag_id}/dagRuns"
        try:
            response = httpx.post(url, auth=self.auth, json={"conf": conf or {}}, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    def clear_task_instance(self, dag_id: str, dag_run_id: str, task_id: str) -> Dict[str, Any]:
        """Clears a task instance to trigger a retry."""
        url = f"{self.base_url}/api/v1/dags/{dag_id}/clearTaskInstances"
        payload = {
            "dry_run": False,
            "task_ids": [task_id],
            "dag_run_id": dag_run_id,
            "include_upstream": False,
            "include_downstream": False,
            "include_future": False,
            "include_past": False,
            "reset_dag_runs": True
        }
        try:
            response = httpx.post(url, auth=self.auth, json=payload, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            if hasattr(e, 'response') and e.response:
                 return {"error": f"HTTP error {e.response.status_code}: {e.response.text}"}
            return {"error": str(e)}

# Tool Wrapper Functions for Agent
def get_airflow_dag_status(dag_id: str, dag_run_id: str) -> str:
    """Fetches the status of a specific Airflow DAG run. Useful to see if it's currently failing or finished."""
    client = AirflowClient()
    res = client.get_dag_run(dag_id, dag_run_id)
    return str(res)

def get_airflow_logs(dag_id: str, dag_run_id: str, task_id: str) -> str:
    """Fetches logs for a failed task in Airflow. This is the first step in diagnosis."""
    client = AirflowClient()
    # Assume try_number 1 for simplicity in this iteration
    return client.get_task_log(dag_id, dag_run_id, task_id, try_number=1)

from ...database import db

def retry_airflow_pipeline(dag_id: str, incident_id: str, dag_run_id: Optional[str] = None, task_id: Optional[str] = None, conf: Optional[Dict[str, Any]] = None) -> str:
    """Triggers a retry of the pipeline.
    
    If dag_run_id and task_id are provided, it clears the specific task instance (targeted retry).
    Otherwise, it triggers a new run of the DAG (full retry).
    
    Requires incident_id for internal tracking. Max retries: 3.
    """
    # Check internal retry guardrail
    # We use the dag_id (or task_id if specific) as the tracker component
    tracker_component = f"{dag_id}:{task_id}" if task_id else dag_id
    current_retries = db.increment_retry_count(incident_id, tracker_component)
    max_allowed = config.agent.max_retries
    
    if current_retries > max_allowed:
        return f"RETRY_DENIED: You have already attempted to retry {tracker_component} {max_allowed} times for incident {incident_id}. DO NOT retry again. Please create a ticket instead."

    client = AirflowClient()
    
    if dag_run_id and task_id:
        # Targeted Task Retry
        print(f"Attempting targeted task retry for {dag_id}/{task_id} in run {dag_run_id}...")
        res = client.clear_task_instance(dag_id, dag_run_id, task_id)
        return f"Targeted retry successful (Attempt {current_retries}/{max_allowed}): {res}"
    else:
        # Full DAG Retry (Fallback)
        print(f"Attempting full DAG retry for {dag_id} (missing run_id or task_id)...")
        # Propagate incident_id in conf for lineage tracking
        conf = conf or {}
        conf["parent_incident_id"] = incident_id
        res = client.trigger_dag(dag_id, conf)
        return f"Full DAG retry triggered (Attempt {current_retries}/{max_allowed}): {res}"
