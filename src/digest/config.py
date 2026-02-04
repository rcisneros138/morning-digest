from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://digest:digest_local@localhost:5432/morning_digest"
    database_url_sync: str = "postgresql://digest:digest_local@localhost:5432/morning_digest"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"

    model_config = {"env_file": ".env"}


settings = Settings()
