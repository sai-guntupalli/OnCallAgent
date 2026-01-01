import sys
import os
import uuid
from typing import Dict, Any

# Add src to python path
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from src.database import db, RetryTracker
from src.config import config
from src.agent.tools.airflow import retry_airflow_pipeline

def test_task_level_retry():
    print("--- Testing Task-Level Retry (Clear Task Instance) ---")
    incident_id = f"TASK-RETRY-TEST-{str(uuid.uuid4())[:4]}"
    dag_id = "sample_failing_dag"
    run_id = "manual__2026-01-01T00:00:00"
    task_id = "process_data"
    
    print(f"Incident ID: {incident_id}")
    
    # 1. Test Targeted Retry (should call clear_task_instance)
    print("\nAttempt 1: Targeted retry with run_id and task_id...")
    res1 = retry_airflow_pipeline(dag_id, incident_id, dag_run_id=run_id, task_id=task_id)
    print(f"Result: {res1}")
    
    # 2. Test Fallback (should call trigger_dag)
    print("\nAttempt 2: Fallback retry without run_id...")
    res2 = retry_airflow_pipeline(dag_id, incident_id)
    print(f"Result: {res2}")
    
    # 3. Test Guardrail (Attempt 4 should fail)
    print("\nAttempt 3 & 4: Checking guardrail with targeted retry...")
    retry_airflow_pipeline(dag_id, incident_id, dag_run_id=run_id, task_id=task_id) # Attempt 2 for this component (dag:task)
    res4 = retry_airflow_pipeline(dag_id, incident_id, dag_run_id=run_id, task_id=task_id) # Attempt 3
    res5 = retry_airflow_pipeline(dag_id, incident_id, dag_run_id=run_id, task_id=task_id) # Attempt 4 -> DENIED
    
    print(f"Attempt 4 Result: {res5}")
    
    if "RETRY_DENIED" in res5:
        print("✅ SUCCESS: Guardrail blocked the 4th attempt for the specific task.")
    else:
        print("❌ FAILURE: Guardrail did not block the 4th attempt.")

    # Check DB counts
    session = db.Session()
    trackers = session.query(RetryTracker).filter(RetryTracker.incident_id == incident_id).all()
    print("\nDB Retry Counts:")
    for t in trackers:
        print(f"  Component {t.task_id}: {t.retry_count}")
    session.close()

if __name__ == "__main__":
    test_task_level_retry()
