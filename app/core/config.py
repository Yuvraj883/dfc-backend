from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Delhi Fried Chicken API"
    database_url: str = "postgresql+asyncpg://dfc:dfc_dev_password@localhost:5432/dfc"
    redis_url: str = "redis://localhost:6379/0"
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    secret_key: str = "dev-secret-change-in-production"
    frontend_url: str = "http://localhost:3000"
    access_token_expire_minutes: int = 60 * 24
    refresh_token_expire_days: int = 7
    table_session_hours: int = 3
    gst_rate: float = 0.05
    loyalty_points_per_rupee: int = 1
    mock_payments: bool = True
    mock_email: bool = True
    google_client_id: str = ""
    google_client_secret: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    sendgrid_api_key: str = ""
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""


settings = Settings()
