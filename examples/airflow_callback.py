import requests
import json
from airflow.operators.python import PythonOperator
from airflow import DAG
from datetime import datetime

# --- Agent Integration Code ---

AGENT_API_URL = "http://localhost:8000/analyze"

def notify_oncall_agent(context):
    """
    Callback function to be executed on task failure.
    Sends details to the OnCall Agent API.
    """
    task_instance = context.get('task_instance')
    dag_run = context.get('dag_run')
    exception = context.get('exception')
    
    # Extract logs (simplified - usually requires reading from remote storage or log API)
    # Here we just send the exception message
    log_snippet = str(exception)
    
    payload = {
        "source_system": "airflow",
        "incident_id": f"{dag_run.run_id}::{task_instance.task_id}",
        "title": f"Airflow Task Failed: {task_instance.task_id}",
        "description": f"DAG: {dag_run.dag_id} failed on task {task_instance.task_id}. Exception: {exception}",
        "logs": log_snippet,
        "metadata": {
            "dag_id": dag_run.dag_id,
            "run_id": dag_run.run_id,
            "task_id": task_instance.task_id,
            "try_number": task_instance.try_number
        }
    }
    
    try:
        response = requests.post(AGENT_API_URL, json=payload, timeout=5)
        print(f"Sent alert to OnCall Agent: {response.status_code}")
    except Exception as e:
        print(f"Failed to alert OnCall Agent: {e}")

# --- Example DAG Usage ---

default_args = {
    'owner': 'data_eng',
    'start_date': datetime(2024, 1, 1),
    'on_failure_callback': notify_oncall_agent  # <--- Register Global Callback
}

with DAG('example_failing_dag', default_args=default_args, schedule_interval='@daily') as dag:
    
    def failing_task():
        raise ValueError("Simulated Cluster Connection Error")

    t1 = PythonOperator(
        task_id='etl_step_1',
        python_callable=failing_task
    )
