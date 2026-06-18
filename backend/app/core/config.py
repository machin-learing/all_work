from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Text Rewrite Demo"
    secret_key: str = "change-this-secret-key"
    access_token_expire_minutes: int = 720
    frontend_origin: str = "http://localhost:5173"

    database_url: str = "mysql+pymysql://root:123456@127.0.0.1:3306/text_rewrite_demo?charset=utf8mb4"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    lora_model_dir: str = "../finetune/output"
    lora_base_model: str = "../finetune/models/mt0-large"
    lora_precision: str = "fp16"

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8")


settings = Settings()
