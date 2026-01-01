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
    max_retries: int = 3
    smart_log_trimming: bool = True

class PathsConfig(BaseModel):
    knowledge_base: str = "./data/knowledge_base"
    database: str = "./data/audit.duckdb" # Fallback/Legacy

class DatabaseConfig(BaseModel):
    db_type: str = Field("postgresql", validation_alias="DB_TYPE")
    host: str = Field("localhost", validation_alias="DB_HOST")
    port: int = Field(5432, validation_alias="DB_PORT")
    name: str = Field("oncall_db", validation_alias="DB_NAME")
    user: str = Field("oncall_user", validation_alias="DB_USER")
    password: str = Field("oncall_password", validation_alias="DB_PASSWORD")

    @property
    def url(self) -> str:
        if self.db_type == "postgresql":
            return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
        # Fallback to duckdb if configured
        return f"duckdb:///{config.paths.database}"

class TicketingConfig(BaseModel):
    system: str = "mock"
    default_queue: str = "DE_ONCALL"

class ToolConfig(BaseModel):
    enabled: bool = True
    timeout: int = 30

class AppConfig(BaseSettings):
    agent: AgentConfig = Field(default_factory=AgentConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
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
    config_obj = AppConfig(**yaml_data)
    
    # Simple, explicit overrides from Env for the crucial LLM selection
    env_model = os.getenv("LLM_MODEL")
    if env_model:
        config_obj.agent.model = env_model
        config_obj.llm_model = env_model
        
    env_key = os.getenv("LLM_KEY")
    if env_key:
        config_obj.llm_key = env_key

    # DB Overrides
    if os.getenv("DB_TYPE"): config_obj.database.db_type = os.getenv("DB_TYPE")
    if os.getenv("DB_HOST"): config_obj.database.host = os.getenv("DB_HOST")
    if os.getenv("DB_PORT"): config_obj.database.port = int(os.getenv("DB_PORT"))
    if os.getenv("DB_NAME"): config_obj.database.name = os.getenv("DB_NAME")
    if os.getenv("DB_USER"): config_obj.database.user = os.getenv("DB_USER")
    if os.getenv("DB_PASSWORD"): config_obj.database.password = os.getenv("DB_PASSWORD")
            
    return config_obj

# Singleton instance
try:
    config = load_config()
except Exception as e:
    print(f"Warning: Configuration load failed: {e}. Using defaults.")
    config = AppConfig(
        agent=AgentConfig(),
        paths=PathsConfig(),
        database=DatabaseConfig(),
        ticketing=TicketingConfig(),
        tools={}
    )
