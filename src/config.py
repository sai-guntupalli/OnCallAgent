import os
import yaml
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Explicitly load .env into os.environ, allowing it to override existing session variables
load_dotenv(override=True)

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
    agent: AgentConfig = Field(default_factory=AgentConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    ticketing: TicketingConfig = Field(default_factory=TicketingConfig)
    tools: Dict[str, ToolConfig] = Field(default_factory=dict)
    
    # Environment variable overrides
    airflow_url: Optional[str] = None
    airflow_username: Optional[str] = None
    airflow_password: Optional[str] = None
    
    databricks_host: Optional[str] = None
    databricks_token: Optional[str] = None
    
    snowflake_account: Optional[str] = None
    snowflake_user: Optional[str] = None
    snowflake_password: Optional[str] = None
    
    # LLM Dynamic Config (Explicitly mapped to Env Vars)
    llm_model: Optional[str] = Field(None, validation_alias="LLM_MODEL")
    llm_key: Optional[str] = Field(None, validation_alias="LLM_KEY")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="")

def load_config(config_path: str = "config.yaml") -> AppConfig:
    yaml_data = {}
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            yaml_data = yaml.safe_load(f) or {}
    
    # Initialize config from YAML and environment variables
    config = AppConfig(**yaml_data)
    
    # Simple, explicit overrides from Env for the crucial LLM selection
    env_model = os.getenv("LLM_MODEL")
    if env_model:
        config.agent.model = env_model
        config.llm_model = env_model
        
    env_key = os.getenv("LLM_KEY")
    if env_key:
        config.llm_key = env_key
            
    return config

# Singleton instance
try:
    config = load_config()
except Exception as e:
    print(f"Warning: Configuration load failed: {e}. Using defaults.")
    config = AppConfig(
        agent=AgentConfig(),
        paths=PathsConfig(),
        ticketing=TicketingConfig(),
        tools={}
    )
