import os

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

basedir = os.path.abspath(os.path.dirname(__file__))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    TELEGRAM_BOT_TOKEN: str
    GITHUB_TOKEN: str | None = None
    SITE_URL: str | None = None
    SQLALCHEMY_DATABASE_URI: str = Field(default=f"sqlite:///{basedir}/data/db.sqlite", alias="DATABASE_URI")
    SQLALCHEMY_ECHO: bool = Field(alias="SQL_DEBUG", default=False)
    LOG_LEVEL: str = "INFO"

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    MAX_REPOS_PER_CHAT: int = 0
    GITHUB_POLL_INTERVAL: int = 60
    CHAT_ID: list[int] = Field(default_factory=list)

    @field_validator("CHAT_ID", mode="before")
    @classmethod
    def split_chat_ids(cls, value):
        if isinstance(value, str):
            return [int(x.strip()) for x in value.split(",")]
        return value

    @computed_field
    @property
    def PROCESS_PRE_RELEASES(self) -> bool:
        return bool(self.GITHUB_TOKEN)


settings = Settings()
