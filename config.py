from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BOT_TOKEN: str
    OWNER_ID: int
    DATABASE_URL: str
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    DOWNLOAD_PATH: str = "/tmp/downloads"
    MAX_RETRIES: int = 3
    DOWNLOAD_JOB_TIMEOUT: int = 900
    DEV_MODE: bool = False
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
