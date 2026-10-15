from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CODEPET_", env_file=".env", extra="ignore")
    token: SecretStr
    ollama_url: str = "http://127.0.0.1:11434"
    provider: Literal["ollama", "codex", "hybrid"] = "ollama"
    codex_model: str = Field(default="", pattern=r"^$|^[A-Za-z0-9][A-Za-z0-9._/-]{0,79}$")
    model: str = ""
    projects: dict[str, Path] = Field(default_factory=dict)
    database: Path = Path(".codepet/memory.db")
    skills_dir: Path = Path("~/.config/codepet-ai/skills")
    retention: bool = True
    proactive: bool = False
    context_chars: int = Field(default=12000, ge=2000, le=32000)
    num_ctx: int = Field(default=4096, ge=2048, le=16384)
    num_predict: int = Field(default=768, ge=64, le=4096)
    ollama_keep_alive_minutes: int = Field(default=15, ge=1, le=120)
    request_timeout: float = Field(default=180, ge=5, le=600)
    max_connections: int = Field(default=8, ge=1, le=32)
    screen_capture: bool = False
    screen_capture_max_bytes: int = Field(default=4_000_000, ge=256_000, le=12_000_000)
    test_sandbox: Literal["bubblewrap", "none"] = "bubblewrap"

    @field_validator("token")
    @classmethod
    def strong_token(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("Generate CODEPET_TOKEN with scripts/bootstrap.py (32+ characters)")
        return value

    @field_validator("ollama_url")
    @classmethod
    def local_ollama(cls, value: str) -> str:
        url = urlparse(value)
        if (
            url.scheme != "http"
            or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("Ollama must use a local HTTP origin")
        return value.rstrip("/")

    @field_validator("projects")
    @classmethod
    def valid_projects(cls, values: dict[str, Path]) -> dict[str, Path]:
        for name, path in values.items():
            if not name or len(name) > 80 or not path.is_absolute() or not path.is_dir():
                raise ValueError("Each project needs an ID and an existing absolute directory")
        return {name: path.resolve() for name, path in values.items()}
