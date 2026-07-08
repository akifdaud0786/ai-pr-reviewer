"""
Centralized configuration for every microservice.
All settings are pulled from environment variables (see .env.example).
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres
    database_url: str = "postgresql+asyncpg://pruser:prpassword@localhost:5432/pr_reviewer"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_always_eager: bool = False

    # GitHub App
    github_app_id: str = ""
    github_app_private_key_path: str = ""
    github_app_private_key: str = ""
    github_webhook_secret: str = "changeme-webhook-secret"
    github_api_base: str = "https://api.github.com"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None  # override for Azure OpenAI / a proxy / local testing

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Internal service URLs
    gateway_internal_url: str = "http://webhook_service:8001"
    reviewer_service_url: str = "http://reviewer_service:8002"
    learner_service_url: str = "http://learner_service:8003"

    log_level: str = "INFO"
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
