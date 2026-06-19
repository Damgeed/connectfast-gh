from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # Paystack
    paystack_secret_key: str = ""
    paystack_public_key: str = ""

    # Database
    database_url: str = "sqlite:///./kemdp.db"

    # Telecom API
    telecom_api_key: str = ""
    telecom_api_url: str = ""

    # App
    app_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:8000,http://127.0.0.1:5500,https://damgeed.github.io"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
