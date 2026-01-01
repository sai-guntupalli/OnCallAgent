# Data Engineering OnCall Agent

An AI-powered agent designed to automate the diagnosis and resolution of data engineering incidents. Built with `google-adk`, `python 3.12`, and `uv`.

## Features
- **Auto-Triage**: Analyzes Airflow, Databricks, and Snowflake failure logs.
- **Smart Remediation**: Retries transient failures, tickets permanent ones.
- **Audit Trail**: Logs all actions to a local DuckDB instance.
- **Pluggable Architecture**: Easy to swap LLMs (via config) and Ticketing / DB providers.
- **Mocking**: Built-in support for analyzing mock logs and creating mock tickets for safe testing.

## Prerequisites
- Python >= 3.12
- `uv` package manager (recommended) or `pip`.

## Installation

```bash
# Install dependencies
uv sync
```

## Configuration

1. Copy `.env.example` to `.env` and fill in your details.
```bash
cp .env.example .env
```

2. Edit `config.yaml` to configure tool behavior and paths.

## Usage

### Development Commands (Makefile)
We provide a `Makefile` to simplify common development tasks.

```bash
make help       # Show available commands
make install    # Install dependencies
make test       # Run test suite
make lint       # Run code linting
make run        # Start the Agent CLI
make clean      # Clean temporary files and DB
```

### Running the Agent
You can interact with the agent directly using the CLI:

```bash
make run
```

This will start an interactive session where you can paste error logs or describe incidents.

**Example Input:**
> Airflow DAG 'finance_etl' failed. I see 'ClusterUnavailable' error in the logs.

**Mocking**:
To test without connecting to real services, you can provide raw logs in your input. The agent is configured to look for `mock_logs` in tool calls, which allows it to simulate diagnosis.

## 🔌 Airflow Integration

To integrate with Airflow, run the agent as a REST API service and configure your DAGs to send failure alerts.

### 1. Start the API Server
```bash
make api
# Server starts at http://localhost:8000
```

### 2. Configure Airflow Callback
Use `on_failure_callback` in your DAGs to trigger the agent.
See `examples/airflow_callback.py` for a copy-paste implementation.

```python
# In your DAG file
from airflow_callback import notify_oncall_agent

default_args = {
    'on_failure_callback': notify_oncall_agent
}
```

The callback will send:
- `dag_id`, `task_id`, `run_id`
- Exception message to standard logs
- Metadata for the agent to use in `get_airflow_logs` tool calls.

## Architecture

- **`src.server`**: FastAPI REST endpoint.
- **`src.main`**: CLI Entry point.
- **`src.agent.core`**: The brain of the agent (ADK Agent definition).
- **`src.agent.tools`**: Integration with external systems (Airflow, DBs, Tickets).
- **`src.database`**: DuckDB singleton for audit logging.
- **`src.config`**: Unified configuration loader.


## Database Schema (DuckDB)
- `audit_logs`: Stores granular details of every agent action and reasoning step.
- `mock_tickets`: Stores tickets created during testing/mock mode.
