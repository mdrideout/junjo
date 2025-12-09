"""
Application settings using Pydantic Settings v2.

Environment variables are loaded from .env file and can be overridden
by actual environment variables.

Pattern validated for high-concurrency asyncio environments.
"""

from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, computed_field, field_validator, model_validator
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


class ParquetIndexerSettings(BaseSettings):
    """Parquet indexer configuration for V4 architecture.

    The indexer polls the filesystem for new Parquet files written by the
    Go ingestion service, reads span metadata, and indexes it into DuckDB.
    """

    parquet_storage_path: Annotated[
        str,
        Field(
            default="../.dbdata/parquet",
            description="Path to Parquet files (shared with Go ingestion)",
            validation_alias="JUNJO_PARQUET_STORAGE_PATH",
        ),
    ]
    poll_interval: Annotated[
        int,
        Field(
            default=30,
            ge=5,
            le=3600,
            description="Indexer polling interval in seconds",
            validation_alias="INDEXER_POLL_INTERVAL",
        ),
    ]
    batch_size: Annotated[
        int,
        Field(
            default=10,
            ge=1,
            le=100,
            description="Maximum files to index per poll cycle",
            validation_alias="INDEXER_BATCH_SIZE",
        ),
    ]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def parquet_storage_path_resolved(self) -> str:
        """Resolved absolute path for Parquet storage.

        Returns:
            Absolute path to Parquet storage directory.
        """
        abs_path = Path(self.parquet_storage_path).resolve()
        return str(abs_path)

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )


class AppSettings(BaseSettings):
    """Main application settings"""

    # Environment
    junjo_env: Annotated[
        str,
        Field(
            default="development",
            description="Environment (development/production)",
            validation_alias="JUNJO_ENV",
        ),
    ]

    # Session Security
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

    # Production URL Configuration
    prod_frontend_url: Annotated[
        str | None,
        Field(
            default=None,
            description="Production frontend URL (e.g., https://app.example.com)",
            validation_alias="JUNJO_PROD_FRONTEND_URL",
        ),
    ]
    prod_backend_url: Annotated[
        str | None,
        Field(
            default=None,
            description="Production backend URL (e.g., https://api.example.com)",
            validation_alias="JUNJO_PROD_BACKEND_URL",
        ),
    ]
    prod_ingestion_url: Annotated[
        str | None,
        Field(
            default=None,
            description="Production ingestion service URL (e.g., https://ingestion.example.com)",
            validation_alias="JUNJO_PROD_INGESTION_URL",
        ),
    ]

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
    # IMPORTANT: Cannot use "*" with credentials=True (session cookies)
    cors_origins: Annotated[
        str | list[str],
        Field(
            default=["http://localhost:5151", "http://localhost:5153"],
            description="Allowed CORS origins (comma-separated string or list)",
            validation_alias=AliasChoices("junjo_allow_origins", "cors_origins"),
        ),
    ]

    # Nested settings
    database: Annotated[
        DatabaseSettings, Field(default_factory=DatabaseSettings, description="Database settings")
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
    parquet_indexer: Annotated[
        ParquetIndexerSettings,
        Field(default_factory=ParquetIndexerSettings, description="V4 Parquet indexer settings"),
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def otlp_endpoint(self) -> str:
        """OTLP ingestion endpoint.

        Returns the production ingestion URL if set, otherwise defaults to localhost
        for development. The ingestion service is a separate container with its own
        public URL (e.g., https://ingestion.example.com). Reverse proxy (Caddy) handles
        internal port mapping to gRPC port 50051.
        """
        if self.prod_ingestion_url:
            return self.prod_ingestion_url

        # Fallback for development
        return "grpc://localhost:50051"

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

    @model_validator(mode="after")
    def validate_production_configuration(self) -> "AppSettings":
        """Validate production URLs and configuration."""
        if self.junjo_env != "production":
            return self

        # Validate production URLs are set
        if not self.prod_frontend_url:
            raise ValueError(
                "PROD_FRONTEND_URL is required when JUNJO_ENV=production. "
                "See .env.example and docs/DEPLOYMENT.md for configuration details."
            )

        if not self.prod_backend_url:
            raise ValueError(
                "PROD_BACKEND_URL is required when JUNJO_ENV=production. "
                "See .env.example and docs/DEPLOYMENT.md for configuration details."
            )

        if not self.prod_ingestion_url:
            raise ValueError(
                "PROD_INGESTION_URL is required when JUNJO_ENV=production. "
                "See .env.example and docs/DEPLOYMENT.md for configuration details."
            )

        # Validate URL formats
        for url_field, url_value in [
            ("prod_frontend_url", self.prod_frontend_url),
            ("prod_backend_url", self.prod_backend_url),
            ("prod_ingestion_url", self.prod_ingestion_url),
        ]:
            if url_value and not url_value.startswith(("http://", "https://")):
                raise ValueError(
                    f"{url_field} must start with http:// or https://. Got: {url_value}"
                )

        # Validate same domain for session cookies
        if self.prod_frontend_url and self.prod_backend_url:
            from urllib.parse import urlparse

            import tldextract

            frontend_parsed = urlparse(self.prod_frontend_url)
            backend_parsed = urlparse(self.prod_backend_url)

            # Extract registrable domains (eTLD+1)
            frontend_extract = tldextract.extract(frontend_parsed.netloc)
            backend_extract = tldextract.extract(backend_parsed.netloc)

            frontend_domain = f"{frontend_extract.domain}.{frontend_extract.suffix}"
            backend_domain = f"{backend_extract.domain}.{backend_extract.suffix}"

            if frontend_domain != backend_domain:
                raise ValueError(
                    f"Frontend and backend must share the same registrable domain for session cookies to work.\n"
                    f"  Frontend domain: {frontend_domain} (from {self.prod_frontend_url})\n"
                    f"  Backend domain: {backend_domain} (from {self.prod_backend_url})\n"
                    f"  Supported configurations:\n"
                    f"    ✅ app.example.com + api.example.com (same domain)\n"
                    f"    ✅ example.com + api.example.com (same domain)\n"
                    f"    ❌ app.example.com + service.run.app (different domains - WILL NOT WORK)\n"
                    f"  See docs/DEPLOYMENT.md for deployment architecture requirements."
                )

        # Auto-derive CORS origins from frontend URL in production
        # Only auto-derive if not explicitly set (still using default localhost origins)
        default_localhost_origins = ["http://localhost:5151", "http://localhost:5153"]
        if not self.cors_origins or self.cors_origins == default_localhost_origins:
            if self.prod_frontend_url:
                self.cors_origins = [self.prod_frontend_url]
                # Note: We'll log this auto-derivation in deployment_validation.py

        return self

    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global settings instance (singleton, loaded once at import)
settings = AppSettings()
