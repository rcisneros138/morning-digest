from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://digest:digest_local@localhost:5432/morning_digest"
    database_url_sync: str = "postgresql://digest:digest_local@localhost:5432/morning_digest"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    llm_temperature: float = 0.2
    llm_timeout: int = 30

    model_config = {"env_file": ".env"}


settings = Settings()
