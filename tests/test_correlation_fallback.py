import sys
import os
import uuid
import time

# Mock the database and incident request to test the server logic directly
from src.database import db
from src.server import analyze_incident, IncidentRequest

class MockBackgroundTasks:
    def add_task(self, func, *args, **kwargs):
        pass

async def test_fallback_correlation():
    print("--- Testing Fallback Incident Correlation (DB Lookup) ---")
    
    external_id = f"RUN-{str(uuid.uuid4())[:8]}::task-1"
    bg = MockBackgroundTasks()

    # 1. First request for a new incident
    print(f"\nRequest 1: Initial failure for {external_id}")
    req1 = IncidentRequest(
        source_system="airflow",
        incident_id=external_id,
        title="Failed Task",
        description="First attempt failed",
        metadata={} # No parent_incident_id
    )
    res1 = await analyze_incident(req1, bg)
    id1 = res1["incident_id"]
    print(f"Assigned ID: {id1}")

    # Small delay to ensure DB commit visibility (though it's synchronous in our impl)
    time.sleep(1)

    # 2. Second request for the same incident (simulating retry failure without metadata)
    print(f"\nRequest 2: Second failure for {external_id} (Missing Metadata)")
    req2 = IncidentRequest(
        source_system="airflow",
        incident_id=external_id,
        title="Failed Task",
        description="Second attempt failed",
        metadata={} # Metadata propagation failed!
    )
    res2 = await analyze_incident(req2, bg)
    id2 = res2["incident_id"]
    print(f"Assigned ID: {id2}")

    if id1 == id2:
        print("\n✅ SUCCESS: Lineage recovered via DB lookup!")
    else:
        print(f"\n❌ FAILURE: Lineage tracking failed. New ID generated: {id2}")

    # 3. Third request for a DIFFERENT incident
    print(f"\nRequest 3: New failure for a DIFFERENT task")
    external_id_new = f"RUN-{str(uuid.uuid4())[:8]}::task-2"
    req3 = IncidentRequest(
        source_system="airflow",
        incident_id=external_id_new,
        title="New Failed Task",
        description="Different task",
        metadata={}
    )
    res3 = await analyze_incident(req3, bg)
    id3 = res3["incident_id"]
    print(f"Assigned ID: {id3}")

    if id3 != id1:
        print("✅ SUCCESS: Correctly generated new ID for different external ID.")
    else:
        print("❌ FAILURE: Incorrectly reused ID for different external ID.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_fallback_correlation())
