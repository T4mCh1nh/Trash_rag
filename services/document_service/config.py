from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_hostname: str
    database_port: str
    database_password: str
    database_name: str
    database_username: str

    openai_api_key: str
    embedding_model: str
    embedding_dim: int

    upload_dir: str = "uploads"

    redis_url: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
