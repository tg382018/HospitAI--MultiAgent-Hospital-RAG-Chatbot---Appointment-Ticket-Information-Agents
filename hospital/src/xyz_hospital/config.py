"""Service configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="XYZ_",
        env_file=(".env", _ROOT / ".env"),
        extra="ignore",
    )

    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/xyz_hospital.db",
        description="Async SQLite URL (relative to cwd unless absolute).",
    )
    hospital_available: bool = Field(default=True, description="If false, POST returns unavailable.")


def get_settings() -> Settings:
    return Settings()
