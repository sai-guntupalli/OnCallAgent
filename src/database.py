from sqlalchemy import create_engine, Column, String, DateTime, JSON, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from .config import config

Base = declarative_base()

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    agent_name = Column(String)
    action_type = Column(String)
    details = Column(JSON)
    status = Column(String)

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

    def log_action(self, action_type: str, details: Dict[str, Any], status: str = "success"):
        """Log an agent action to the audit table."""
        session = self.Session()
        try:
            log_entry = AuditLog(
                id=str(uuid.uuid4()),
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

# Singleton
db = Database()
