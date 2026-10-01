from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./medsure.db"
    jwt_secret: str = "change-me"
    jwt_hours: int = 24 * 30
    base_url: str = "http://localhost:8000"

    ack_window_seconds: int = 60
    cancel_window_seconds: int = 0
    poll_seconds: float = 2.0
    run_worker_in_api: bool = False

    dev_mode: bool = True
    dev_otp: str = ""
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 5

    fcm_credentials_file: str = ""

    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_sms_from: str = ""
    twilio_validate_signature: bool = True

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "MedSure <no-reply@example.com>"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
