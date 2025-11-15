from __future__ import annotations

import os
from typing import List, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AnyUrl, AliasChoices, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    cors_origins: list[str] = (
        os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    )

    # App info
    APP_NAME: str = "QuizzyLive Backend"
    API_V1_PREFIX: str = "/api/v1"

    APP_ENV: str = Field(
        "dev",
        validation_alias=AliasChoices("APP_ENV", "app_env"),
        description="Application environment: dev|staging|prod",
    )

    BACKEND_PORT: int = Field(
        8000,
        validation_alias=AliasChoices("BACKEND_PORT", "app_port"),
        description="Backend port to bind",
    )

    # Supabase
    SUPABASE_URL: AnyUrl = Field(
        ...,
        validation_alias=AliasChoices("SUPABASE_URL", "supabase_url"),
        description="Your Supabase project URL",
    )

    SUPABASE_SERVICE_ROLE_KEY: str = Field(
        ...,
        validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY", "supabase_service_role_key"),
        description="Service role key (server-side)",
    )

    SUPABASE_ANON_KEY: str | None = Field(
        None,
        validation_alias=AliasChoices("SUPABASE_ANON_KEY", "supabase_anon_key"),
        description="Public anon key (optional)",
    )

    SUPABASE_SCHEMA: str = Field(
        "public",
        validation_alias=AliasChoices("SUPABASE_SCHEMA", "supabase_schema"),
        description="Supabase schema name",
    )

    # CORS
    FRONTEND_ORIGINS: list[str] = [
        *[f"http://localhost:{p}" for p in range(5173, 5191)],
        *[f"http://127.0.0.1:{p}" for p in range(5173, 5191)],
    ]

    @field_validator("FRONTEND_ORIGINS", mode="before")
    @classmethod
    def _parse_origins(cls, v: Any) -> Any:
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("[") and s.endswith("]"):
                import json
                try:
                    return json.loads(s)
                except Exception:
                    pass
            return [item.strip() for item in s.replace(";", ",").split(",") if item.strip()]
        return v


    GRPC_HOST: str = Field(
        "localhost",
        validation_alias=AliasChoices("GRPC_HOST", "grpc_host"),
    )
    GRPC_PORT: int = Field(
        50051,
        validation_alias=AliasChoices("GRPC_PORT", "grpc_port"),
    )


settings = Settings()
