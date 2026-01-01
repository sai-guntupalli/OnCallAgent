import duckdb
import json
import uuid
import time
import contextlib
from datetime import datetime
from typing import Dict, Any, List, Optional
from .config import config

class Database:
    def __init__(self):
        self.db_path = config.paths.database
        self._init_db()

    @contextlib.contextmanager
    def _get_con(self, read_only: bool = False):
        """
        Provides a DuckDB connection on-demand.
        Includes a retry loop to handle lock contention from other processes.
        """
        con = None
        max_retries = 10
        retry_delay = 0.5
        
        for i in range(max_retries):
            try:
                con = duckdb.connect(self.db_path, read_only=read_only)
                yield con
                return
            except duckdb.IOException as e:
                if "Could not set lock" in str(e) and i < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                raise
            finally:
                if con:
                    con.close()

    def _init_db(self):
        # Create directory if it doesn't exist
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with self._get_con() as con:
            # Create Audit Log Table
            con.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id VARCHAR,
                    timestamp TIMESTAMP,
                    agent_name VARCHAR,
                    action_type VARCHAR,
                    details JSON,
                    status VARCHAR
                )
            """)
            
            # Create Mock Tickets Table
            con.execute("""
                CREATE TABLE IF NOT EXISTS mock_tickets (
                    ticket_id VARCHAR,
                    created_at TIMESTAMP,
                    title VARCHAR,
                    description VARCHAR,
                    status VARCHAR,
                    priority VARCHAR,
                    queue VARCHAR,
                    resolution_guide VARCHAR
                )
            """)
            
            # Ensure column exists if table was already created
            try:
                con.execute("ALTER TABLE mock_tickets ADD COLUMN resolution_guide VARCHAR")
            except:
                pass

    def log_action(self, action_type: str, details: Dict[str, Any], status: str = "success"):
        """Log an agent action to the audit table."""
        try:
            log_id = str(uuid.uuid4())
            timestamp = datetime.now()
            details_json = json.dumps(details, default=str)
            
            with self._get_con() as con:
                con.execute("""
                    INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?)
                """, (log_id, timestamp, config.agent.name, action_type, details_json, status))
        except Exception as e:
            print(f"Failed to write to audit log: {e}")

    def create_ticket(self, title: str, description: str, priority: str = "Medium", resolution_guide: Optional[str] = None) -> str:
        """Create a ticket in the mock system."""
        ticket_id = f"TICKET-{str(uuid.uuid4())[:8].upper()}"
        timestamp = datetime.now()
        
        with self._get_con() as con:
            con.execute("""
                INSERT INTO mock_tickets VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (ticket_id, timestamp, title, description, "OPEN", priority, config.ticketing.default_queue, resolution_guide))
        
        return ticket_id
        
    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        with self._get_con(read_only=True) as con:
            result = con.execute("SELECT * FROM mock_tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
            if result:
                cols = [desc[0] for desc in con.description]
                return dict(zip(cols, result))
        return None

# Singleton
db = Database()
