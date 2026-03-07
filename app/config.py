"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://costharbor:costharbor@db:5432/costharbor"

    # Security
    secret_key: str = "change-me"
    encryption_key: str = ""

    # Initial admin
    admin_username: str = "admin"
    admin_password: str = "change-me"
    admin_email: str = "admin@example.com"

    # Application
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_env: str = "production"
    log_level: str = "info"

    # File storage
    upload_dir: str = "/data/uploads"
    document_dir: str = "/data/documents"
    max_upload_size_mb: int = 50

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
