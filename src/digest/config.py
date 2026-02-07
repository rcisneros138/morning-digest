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
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 30
    mailgun_api_key: str = ""
    mailgun_domain: str = ""
    mailgun_from_email: str = "Morning Digest <digest@mg.example.com>"
    admin_api_key: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
