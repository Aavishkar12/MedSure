from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    groq_text_model: str = "openai/gpt-oss-120b"
    database_url: str = "sqlite:///./medsure.db"
    upload_dir: str = "./uploads"
    upload_max_size_bytes: int = 25 * 1024 * 1024  # 25 MB limit
    demo_fallback: bool = False
    # Path to the Firebase service-account JSON file, or the JSON itself (handy for hosted env vars).
    firebase_credentials: str = ""
    # Accept the X-User-Id header instead of a Firebase token. Local development only.
    auth_dev_bypass: bool = False


settings = Settings()
