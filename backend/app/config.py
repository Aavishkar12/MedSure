from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    groq_vision_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    groq_text_model: str = "llama-3.3-70b-versatile"
    database_url: str = "sqlite:///./medsure.db"
    upload_dir: str = "./uploads"
    # Path to the Firebase service-account JSON file, or the JSON itself (handy for hosted env vars).
    firebase_credentials: str = ""
    # Accept the X-User-Id header instead of a Firebase token. Local development only.
    auth_dev_bypass: bool = False


settings = Settings()
