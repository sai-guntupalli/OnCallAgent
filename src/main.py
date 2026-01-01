import sys
import asyncio
from .agent.core import run_agent

def main():
    print("🤖 Data Engineering OnCall Agent - CLI Mode")
    print("-------------------------------------------")
    print("Type your incident description below (or 'exit' to quit).")
    print("Example: 'Airflow DAG 'etl_daily' failed on task 'extract' with timeout error.'")
    
    while True:
        try:
            user_input = input("\n> ")
            if user_input.lower() in ["exit", "quit", "q"]:
                print("Exiting...")
                break
                
            if not user_input.strip():
                continue
                
            print(f"\nProcessing incident...")
            
            # Use asyncio.run to call the async agent executor
            response_text = asyncio.run(run_agent(user_input))
            
            print("\n✅ Agent execution complete. Check 'data/audit.duckdb' for logs.")
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()
