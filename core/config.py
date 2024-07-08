from enum import Enum
from pydantic import BaseSettings
from dotenv import load_dotenv
import os

# Load environment variables from .env file if not already loaded
load_dotenv()

class EnvironmentType(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TEST = "test"

class BaseConfig(BaseSettings):
    class Config:
        case_sensitive = True

class Config(BaseConfig):
    DEBUG: int = 0
    DEFAULT_LOCALE: str = "en_US"
    ENVIRONMENT: str = EnvironmentType.DEVELOPMENT
    POSTGRES_URL: str
    CHAT_DB_URL: str
    OPENAI_API_KEY: str = None
    RELEASE_VERSION: str = "0.1.0"
    SHOW_SQL_ALCHEMY_QUERIES: int = 0
    SECRET_KEY: str = "super-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24
    EMAIL: str = "test@pandabi.ai"
    PASSWORD: str = "12345"
    DEFAULT_ORGANIZATION: str = "PandaBI"
    DEFAULT_SPACE: str = "pandasai"

config = Config()
