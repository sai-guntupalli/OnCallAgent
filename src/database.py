import duckdb
import json
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from .config import config

class Database:
    def __init__(self):
        self.db_path = config.paths.database
        self._init_db()

    def _init_db(self):
        # Create directory if it doesn't exist
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        self.con = duckdb.connect(self.db_path)
        
        # Create Audit Log Table
        self.con.execute("""
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
        self.con.execute("""
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
            self.con.execute("ALTER TABLE mock_tickets ADD COLUMN resolution_guide VARCHAR")
        except:
            pass

    def log_action(self, action_type: str, details: Dict[str, Any], status: str = "success"):
        """Log an agent action to the audit table."""
        try:
            log_id = str(uuid.uuid4())
            timestamp = datetime.now()
            details_json = json.dumps(details, default=str)
            
            self.con.execute("""
                INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?)
            """, (log_id, timestamp, config.agent.name, action_type, details_json, status))
        except Exception as e:
            print(f"Failed to write to audit log: {e}")

    def create_ticket(self, title: str, description: str, priority: str = "Medium", resolution_guide: Optional[str] = None) -> str:
        """Create a ticket in the mock system."""
        ticket_id = f"TICKET-{str(uuid.uuid4())[:8].upper()}"
        timestamp = datetime.now()
        
        self.con.execute("""
            INSERT INTO mock_tickets VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (ticket_id, timestamp, title, description, "OPEN", priority, config.ticketing.default_queue, resolution_guide))
        
        return ticket_id
        
    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        result = self.con.execute("SELECT * FROM mock_tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
        if result:
            cols = [desc[0] for desc in self.con.description]
            return dict(zip(cols, result))
        return None

    def close(self):
        self.con.close()

# Singleton
db = Database()
