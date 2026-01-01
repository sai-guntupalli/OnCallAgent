from sqlalchemy import create_engine, Column, String, DateTime, JSON, Text, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from .config import config

Base = declarative_base()

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True)
    incident_id = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    agent_name = Column(String)
    action_type = Column(String)
    details = Column(JSON)
    status = Column(String)

class TokenUsage(Base):
    __tablename__ = "token_usage"
    id = Column(String, primary_key=True)
    incident_id = Column(String, index=True)
    turn_index = Column(Integer)
    model = Column(String)
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    total_tokens = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)

class RetryTracker(Base):
    __tablename__ = "retry_tracker"
    id = Column(String, primary_key=True) # incident_id + task_id
    incident_id = Column(String, index=True)
    task_id = Column(String)
    retry_count = Column(Integer, default=0)

class MockTicket(Base):
    __tablename__ = "mock_tickets"
    ticket_id = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    title = Column(String)
    description = Column(Text)
    status = Column(String)
    priority = Column(String)
    queue = Column(String)
    resolution_guide = Column(Text)

class Database:
    def __init__(self):
        self.engine = create_engine(config.database.url)
        self.Session = sessionmaker(bind=self.engine)
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist."""
        Base.metadata.create_all(self.engine)

    def log_action(self, action_type: str, details: Dict[str, Any], incident_id: Optional[str] = None, status: str = "success"):
        """Log an agent action to the audit table."""
        session = self.Session()
        try:
            log_entry = AuditLog(
                id=str(uuid.uuid4()),
                incident_id=incident_id,
                agent_name=config.agent.name,
                action_type=action_type,
                details=details,
                status=status
            )
            session.add(log_entry)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Failed to write to audit log: {e}")
        finally:
            session.close()

    def track_token_usage(self, incident_id: str, model: str, prompt_tokens: int, completion_tokens: int, total_tokens: int, turn_index: int):
        """Log token usage for a specific turn in an incident."""
        session = self.Session()
        try:
            usage = TokenUsage(
                id=str(uuid.uuid4()),
                incident_id=incident_id,
                turn_index=turn_index,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens
            )
            session.add(usage)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Failed to log token usage: {e}")
        finally:
            session.close()

    def get_retry_count(self, incident_id: str, task_id: str) -> int:
        """Get the number of retries for a specific task in an incident."""
        session = self.Session()
        try:
            tracker_id = f"{incident_id}_{task_id}"
            tracker = session.query(RetryTracker).filter_by(id=tracker_id).first()
            return tracker.retry_count if tracker else 0
        finally:
            session.close()

    def increment_retry_count(self, incident_id: str, task_id: str) -> int:
        """Increment the retry count for a specific task and return the new count."""
        session = self.Session()
        try:
            tracker_id = f"{incident_id}_{task_id}"
            tracker = session.query(RetryTracker).filter_by(id=tracker_id).first()
            if not tracker:
                tracker = RetryTracker(id=tracker_id, incident_id=incident_id, task_id=task_id, retry_count=1)
                session.add(tracker)
            else:
                tracker.retry_count += 1
            session.commit()
            return tracker.retry_count
        except Exception as e:
            session.rollback()
            print(f"Failed to increment retry count: {e}")
            return 0
        finally:
            session.close()

    def create_ticket(self, title: str, description: str, priority: str = "Medium", resolution_guide: Optional[str] = None) -> str:
        """Create a ticket in the mock system."""
        ticket_id = f"TICKET-{str(uuid.uuid4())[:8].upper()}"
        session = self.Session()
        try:
            ticket = MockTicket(
                ticket_id=ticket_id,
                title=title,
                description=description,
                status="OPEN",
                priority=priority,
                queue=config.ticketing.default_queue,
                resolution_guide=resolution_guide
            )
            session.add(ticket)
            session.commit()
            return ticket_id
        except Exception as e:
            session.rollback()
            print(f"Failed to create ticket: {e}")
            raise
        finally:
            session.close()
        
    def get_ticket(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        session = self.Session()
        try:
            ticket = session.query(MockTicket).filter_by(ticket_id=ticket_id).first()
            if ticket:
                return {
                    "ticket_id": ticket.ticket_id,
                    "created_at": ticket.created_at,
                    "title": ticket.title,
                    "description": ticket.description,
                    "status": ticket.status,
                    "priority": ticket.priority,
                    "queue": ticket.queue,
                    "resolution_guide": ticket.resolution_guide
                }
            return None
        finally:
            session.close()

    def lookup_incident_by_external_id(self, external_id: str) -> Optional[str]:
        """Find an existing incident_id by its external identifier (e.g. run_id::task_id)."""
        session = self.Session()
        try:
            # Fetch recent reception logs and filter in Python for portability
            # This avoids dialect-specific JSON query issues (Postgres JSONB vs SQLite JSON vs DuckDB)
            recent_logs = session.query(AuditLog).filter(
                AuditLog.action_type == "API_REQUEST_RECEIVED"
            ).order_by(AuditLog.timestamp.desc()).limit(50).all()
            
            for log in recent_logs:
                if log.details and log.details.get("external_id") == external_id:
                    return log.incident_id
            return None
        except Exception as e:
            print(f"Failed to lookup external_id: {e}")
            return None
        finally:
            session.close()

# Singleton
db = Database()
