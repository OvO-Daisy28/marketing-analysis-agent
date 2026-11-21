from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8-sig", extra="ignore")
    database_url: str = "sqlite:///./data/local.db"
    model_mode: str = "mock"
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = ""
    llm_api_key: str = ""
    tool_arguments_empty_prefix_fix: bool = False
    app_origin: str = "http://localhost:8000"
    cookie_secure: bool = False
    max_steps: int = 20
    max_run_seconds: int = 600
    llm_timeout: int = 90
    max_input_tokens: int = 12000
    max_run_tokens: int = 80000
    max_output_tokens: int = 2048
    worker_concurrency: int = 2
    lease_seconds: int = 120
    input_price_per_million: str = ""
    output_price_per_million: str = ""


settings = Settings()
