"""
Application settings using Pydantic Settings v2.

Environment variables are loaded from .env file and can be overridden
by actual environment variables.

Pattern validated for high-concurrency asyncio environments.
"""

from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_env_file() -> str:
    """
    Find .env file in current directory or parent directory.

    This allows the app to work whether running from:
    - Repository root: /Users/matt/repos/junjo-ai-studio/
    - Backend directory: /Users/matt/repos/junjo-ai-studio/backend/

    Returns:
        Path to .env file (current dir, parent dir, or default ".env")
    """
    current = Path.cwd() / ".env"
    parent = Path.cwd().parent / ".env"

    if current.exists():
        return str(current)
    elif parent.exists():
        return str(parent)
    else:
        # Fallback to default (will use environment variables only)
        return ".env"


class DatabaseSettings(BaseSettings):
    """Database configuration"""

    sqlite_path: Annotated[
        str,
        Field(
            default="../.dbdata/sqlite/junjo.db",
            description="Path to SQLite database file",
            validation_alias="JUNJO_SQLITE_PATH",
        ),
    ]
    duckdb_path: Annotated[
        str,
        Field(
            default="../.dbdata/duckdb/traces.duckdb",
            description="Path to DuckDB database file",
            validation_alias="JUNJO_DUCKDB_PATH",
        ),
    ]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlite_url(self) -> str:
        """Computed SQLite async URL with absolute path.

        Returns:
            SQLite connection URL for async SQLAlchemy engine with absolute path.
        """
        # Resolve to absolute path (handles relative paths from any working directory)
        abs_path = Path(self.sqlite_path).resolve()
        # Ensure parent directory exists
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{abs_path}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duckdb_url(self) -> str:
        """Computed DuckDB async URL with absolute path.

        Returns:
            DuckDB connection URL for async SQLAlchemy engine with absolute path.
        """
        # Resolve to absolute path (handles relative paths from any working directory)
        abs_path = Path(self.duckdb_path).resolve()
        # Ensure parent directory exists
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return f"duckdb+aiosqlite:///{abs_path}"

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


class SessionCookieSettings(BaseSettings):
    """Session cookie and authentication security settings"""

    secure_cookie_key: Annotated[
        str,
        Field(
            description="Base64-encoded 32-byte encryption key for SecureCookiesMiddleware (Fernet/AES-256). "
            "Generate with: openssl rand -base64 32",
            validation_alias="JUNJO_SECURE_COOKIE_KEY",
        ),
    ]
    session_secret: Annotated[
        str,
        Field(
            description="Signing secret for SessionMiddleware (any length). "
            "Generate with: openssl rand -base64 32",
            validation_alias="JUNJO_SESSION_SECRET",
        ),
    ]
    junjo_env: Annotated[
        str,
        Field(
            default="development",
            description="Environment (development/production)",
            validation_alias="JUNJO_ENV",
        ),
    ]
    junjo_prod_auth_domain: Annotated[
        str,
        Field(
            default="",
            description="Production auth domain for subdomain cookie support (e.g., 'junjo.io')",
            validation_alias="JUNJO_PROD_AUTH_DOMAIN",
        ),
    ]

    @field_validator("secure_cookie_key", mode="before")
    @classmethod
    def validate_secure_cookie_key(cls, v: str) -> str:
        """
        Validate secure cookie key is a valid base64 string for Fernet.

        Fernet (used by SecureCookiesMiddleware) requires a base64url-encoded 32-byte key.
        The `openssl rand -base64 32` command generates 32 random bytes and base64-encodes them.

        Args:
            v: Base64-encoded string (from `openssl rand -base64 32`)

        Returns:
            The same base64 string (Fernet will decode it internally)

        Raises:
            ValueError: If key is not valid base64 or not 32 bytes when decoded
        """
        if not isinstance(v, str):
            raise TypeError(f"Expected str, got {type(v)}")

        # Validate it's valid base64 and decodes to 32 bytes
        import base64

        try:
            # Try standard base64 first (openssl rand -base64 uses standard, not urlsafe)
            decoded = base64.b64decode(v)
        except Exception as e:
            raise ValueError(
                "JUNJO_SECURE_COOKIE_KEY must be a valid base64 string. "
                "Generate with: openssl rand -base64 32"
            ) from e

        # Validate exactly 32 bytes for AES-256
        if len(decoded) != 32:
            raise ValueError(
                f"JUNJO_SECURE_COOKIE_KEY must decode to exactly 32 bytes for AES-256 encryption. "
                f"Got {len(decoded)} bytes. Generate with: openssl rand -base64 32"
            )

        return v

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


class IngestionServiceSettings(BaseSettings):
    """Ingestion service gRPC connection settings"""

    host: Annotated[
        str,
        Field(
            default="localhost",
            description="Ingestion service gRPC host",
            validation_alias="INGESTION_HOST",
        ),
    ]
    port: Annotated[
        int,
        Field(
            default=50052,
            ge=1,
            le=65535,
            description="Ingestion service internal gRPC port",
            validation_alias="INGESTION_PORT",
        ),
    ]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def grpc_url(self) -> str:
        """Computed gRPC URL"""
        return f"{self.host}:{self.port}"

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


class SpanIngestionSettings(BaseSettings):
    """Span ingestion poller configuration"""

    INGESTION_HOST: Annotated[
        str,
        Field(
            default="junjo-ai-studio-ingestion",
            description="Ingestion service hostname for span reading",
            validation_alias="INGESTION_HOST",
        ),
    ]
    INGESTION_PORT: Annotated[
        int,
        Field(
            default=50052,
            ge=1,
            le=65535,
            description="Ingestion service gRPC port",
            validation_alias="INGESTION_PORT",
        ),
    ]
    SPAN_POLL_INTERVAL: Annotated[
        int,
        Field(
            default=5,
            ge=1,
            le=3600,
            description="Span polling interval in seconds",
            validation_alias="SPAN_POLL_INTERVAL",
        ),
    ]
    SPAN_BATCH_SIZE: Annotated[
        int,
        Field(
            default=100,
            ge=1,
            le=10000,
            description="Maximum spans to read per poll",
            validation_alias="SPAN_BATCH_SIZE",
        ),
    ]
    SPAN_STRICT_MODE: Annotated[
        bool,
        Field(
            default=False,
            description="If True, fail entire batch on state patch errors",
            validation_alias="SPAN_STRICT_MODE",
        ),
    ]

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


class LLMSettings(BaseSettings):
    """LLM provider API key configuration for LiteLLM"""

    openai_api_key: Annotated[
        str | None, Field(default=None, description="OpenAI API key (starts with sk-)")
    ]
    anthropic_api_key: Annotated[
        str | None, Field(default=None, description="Anthropic API key (starts with sk-ant-)")
    ]
    gemini_api_key: Annotated[
        str | None, Field(default=None, description="Google AI Studio API key for Gemini models")
    ]

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class AppSettings(BaseSettings):
    """Main application settings"""

    # Server
    port: Annotated[
        int,
        Field(
            default=1323,
            ge=1,
            le=65535,
            description="HTTP server port (internal container port, typically 1323)",
            validation_alias="JUNJO_BACKEND_PORT",
        ),
    ]

    # gRPC Server
    GRPC_PORT: Annotated[
        int,
        Field(
            default=50053,
            ge=1,
            le=65535,
            description="gRPC server port for internal authentication (50053)",
        ),
    ]

    # Logging
    log_level: Annotated[
        str,
        Field(
            default="info",
            description="Log level: debug, info, warn, error",
            validation_alias="JUNJO_LOG_LEVEL",
        ),
    ]
    log_format: Annotated[
        str,
        Field(
            default="json",
            description="Log format: json, text",
            validation_alias="JUNJO_LOG_FORMAT",
        ),
    ]

    # CORS
    # Note: Type is str | list[str] to prevent Pydantic Settings from trying
    # to JSON-parse the env var. The validator converts comma-separated strings to list.
    cors_origins: Annotated[
        str | list[str],
        Field(
            default=["http://localhost:5151"],
            description="Allowed CORS origins (comma-separated string or list)",
            validation_alias=AliasChoices("junjo_allow_origins", "cors_origins"),
        ),
    ]

    # Nested settings
    database: Annotated[
        DatabaseSettings, Field(default_factory=DatabaseSettings, description="Database settings")
    ]
    session_cookie: Annotated[
        SessionCookieSettings,
        Field(
            default_factory=SessionCookieSettings,
            description="Session cookie and authentication settings",
        ),
    ]
    ingestion: Annotated[
        IngestionServiceSettings,
        Field(default_factory=IngestionServiceSettings, description="Ingestion service settings"),
    ]
    span_ingestion: Annotated[
        SpanIngestionSettings,
        Field(default_factory=SpanIngestionSettings, description="Span ingestion poller settings"),
    ]
    llm: Annotated[
        LLMSettings,
        Field(default_factory=LLMSettings, description="LLM provider API keys for LiteLLM"),
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        """Parse CORS origins from string or list.

        Args:
            v: Either a JSON string, comma-separated string, or list of origin URLs.

        Returns:
            List of validated CORS origin URLs.
        """
        if isinstance(v, str):
            # Handle JSON array string from env var
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # Fallback to comma-separated
                return [origin.strip() for origin in v.split(",")]
        return v

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance (singleton, loaded once at import)
settings = AppSettings()
