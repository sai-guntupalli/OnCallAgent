import os
import yaml
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class AgentConfig(BaseModel):
    name: str = "DataEngOnCall"
    model: str = "gemini-2.0-flash"

class PathsConfig(BaseModel):
    knowledge_base: str = "./data/knowledge_base"
    database: str = "./data/audit.duckdb"

class TicketingConfig(BaseModel):
    system: str = "mock"
    default_queue: str = "DE_ONCALL"

class ToolConfig(BaseModel):
    enabled: bool = True
    timeout: int = 30

class AppConfig(BaseSettings):
    agent: AgentConfig
    paths: PathsConfig
    ticketing: TicketingConfig
    tools: Dict[str, ToolConfig]
    
    # Environment variable overrides for secrets
    airflow_url: Optional[str] = None
    airflow_username: Optional[str] = None
    airflow_password: Optional[str] = None
    
    databricks_host: Optional[str] = None
    databricks_token: Optional[str] = None
    
    snowflake_account: Optional[str] = None
    snowflake_user: Optional[str] = None
    snowflake_password: Optional[str] = None
    
    # LLM Dynamic Config
    llm_model: Optional[str] = Field(None, validation_alias="LLM_MODEL")
    llm_key: Optional[str] = Field(None, validation_alias="LLM_KEY")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

def load_config(config_path: str = "config.yaml") -> AppConfig:
    with open(config_path, "r") as f:
        yaml_config = yaml.safe_load(f)
    
    # Load config combining YAML and .env
    config = AppConfig(**yaml_config)
    
    # Logic to apply LLM overrides
    if config.llm_model:
        config.agent.model = config.llm_model
        
    if config.llm_key:
        # Heuristic to set the correct env var for common libraries
        # This allows "LLM_KEY" to drive the agent's auth
        if "gemini" in config.agent.model.lower():
            os.environ["GOOGLE_API_KEY"] = config.llm_key
        elif "gpt" in config.agent.model.lower():
            os.environ["OPENAI_API_KEY"] = config.llm_key
            
    return config

# Singleton instance
try:
    config = load_config()
except FileNotFoundError:
    # Fallback for when config.yaml might not exist in current dir (e.g. tests)
    # This logic can be improved.
    print("Warning: config.yaml not found, using defaults where possible.")
    config = AppConfig(
        agent=AgentConfig(),
        paths=PathsConfig(),
        ticketing=TicketingConfig(),
        tools={"airflow": ToolConfig(), "databricks": ToolConfig(), "snowflake": ToolConfig()}
    )
