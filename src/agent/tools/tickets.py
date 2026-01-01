from ...database import db
from typing import Optional, Dict, Any

def create_incident_ticket(title: str, description: str, priority: str = "Medium", resolution_guide: Optional[str] = None) -> str:
    """
    Creates a new support ticket in the ticketing system.
    
    Args:
        title: Short summary of the issue.
        description: Detailed description of the error and analysis.
        priority: Priority level (Low, Medium, High, Critical).
        resolution_guide: Step-by-step guide on how to resolve the issue.
        
    Returns:
        The ID of the created ticket.
    """
    ticket_id = db.create_ticket(title, description, priority, resolution_guide=resolution_guide)
    return f"Ticket created successfully. ID: {ticket_id}"

def update_ticket_status(ticket_id: str, status: str, comment: str) -> str:
    """Updates the status of an existing ticket."""
    # Mock implementation - in real system would call API
    return f"Ticket {ticket_id} updated to {status}. Comment: {comment}"
