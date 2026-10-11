from __future__ import annotations

import os
from dataclasses import dataclass

from app.application.chunking_config import ChunkingSettings


@dataclass(frozen=True)
class Settings:
    app_name: str = "askmydocs-ai"
    app_version: str = "0.1.0"
    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    sec_user_agent: str = ""
    sec_timeout_seconds: float = 20.0
    chunking: ChunkingSettings = ChunkingSettings()

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            app_name=os.getenv("APP_NAME", "askmydocs-ai"),
            app_version=os.getenv("APP_VERSION", "0.1.0"),
            app_env=os.getenv("APP_ENV", "development"),
            host=os.getenv("APP_HOST", "0.0.0.0"),
            port=int(os.getenv("APP_PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            sec_user_agent=os.getenv(
                "SEC_USER_AGENT",
                os.getenv("ASKMYDOCS_SEC_USER_AGENT", ""),
            ),
            sec_timeout_seconds=float(os.getenv("SEC_TIMEOUT_SECONDS", "20")),
            chunking=ChunkingSettings(
                target_chunk_tokens=int(os.getenv("TARGET_CHUNK_TOKENS", "800")),
                max_chunk_tokens=int(os.getenv("MAX_CHUNK_TOKENS", "1000")),
                min_chunk_tokens=int(os.getenv("MIN_CHUNK_TOKENS", "100")),
                overlap_tokens=int(os.getenv("OVERLAP_TOKENS", "100")),
                chunking_version=os.getenv("CHUNKING_VERSION", "1"),
                tokenizer_encoding=os.getenv("TOKENIZER_ENCODING", "cl100k_base"),
            ),
        )


settings = Settings.from_env()


def get_settings() -> Settings:
    return settings
