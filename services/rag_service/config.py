from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_hostname: str
    database_port: str
    database_password: str
    database_name: str
    database_username: str

    gemini_api_key: str
    gemini_model: str

    document_service_url: str = "http://document-service:8000"

    retrieval_top_k: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
