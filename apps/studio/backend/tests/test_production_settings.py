"""Tests for production URL configuration and validation."""

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from app.config.settings import AppSettings

# Valid 32-byte test keys (generated with: openssl rand -base64 32)
TEST_COOKIE_KEY = "2VgT3TJSLHTtLvnvK+KQhNzzwMDtNcZrtIb4Q+BIP5I="
TEST_SESSION_SECRET = "YnVpbHQgd2l0aCBjbGF1ZGUgY29kZSBmb3IgdGVzdGluZwo="


class _IsolatedAppSettings(AppSettings):
    """Test-only subclass that disables environment loading."""

    model_config = SettingsConfigDict(
        env_file=None,
        env_prefix="",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Only use init_settings source (constructor args), ignore all env sources."""
        return (init_settings,)


def create_test_settings(**kwargs):
    """Create AppSettings instance for testing without env loading.

    Note: When using validation_alias in Pydantic Settings, you must pass
    the ALIAS names (e.g., JUNJO_ENV) not the field names (e.g., junjo_env).
    """
    return _IsolatedAppSettings(**kwargs)


class TestProductionURLValidation:
    """Test production URL requirement and validation."""

    def test_production_requires_frontend_url(self):
        """Test that production mode requires JUNJO_PROD_FRONTEND_URL."""
        with pytest.raises(ValidationError, match="PROD_FRONTEND_URL is required"):
            create_test_settings(
                JUNJO_ENV="production",
                JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
                JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
                # Missing: JUNJO_PROD_FRONTEND_URL
                JUNJO_PROD_BACKEND_URL="https://api.example.com",
            )

    def test_production_requires_backend_url(self):
        """Test that production mode requires JUNJO_PROD_BACKEND_URL."""
        with pytest.raises(ValidationError, match="PROD_BACKEND_URL is required"):
            create_test_settings(
                JUNJO_ENV="production",
                JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
                JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
                JUNJO_PROD_FRONTEND_URL="https://app.example.com",
                # Missing: JUNJO_PROD_BACKEND_URL
            )

    def test_url_must_have_protocol(self):
        """Test that URLs must start with http:// or https://."""
        with pytest.raises(ValidationError, match="must start with http"):
            create_test_settings(
                JUNJO_ENV="production",
                JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
                JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
                JUNJO_PROD_FRONTEND_URL="app.example.com",  # Missing protocol
                JUNJO_PROD_BACKEND_URL="https://api.example.com",
                JUNJO_PROD_INGESTION_URL="https://ingestion.example.com",
            )

    def test_development_mode_without_urls(self):
        """Test that development mode works without production URLs."""
        settings = create_test_settings(
            JUNJO_ENV="development",
            JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
            JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
        )
        assert settings.prod_frontend_url is None
        assert settings.prod_backend_url is None


class TestIngestionURLConfiguration:
    """Test ingestion URL configuration."""

    def test_production_requires_ingestion_url(self):
        """Test that production mode requires JUNJO_PROD_INGESTION_URL."""
        with pytest.raises(ValidationError, match="PROD_INGESTION_URL is required"):
            create_test_settings(
                JUNJO_ENV="production",
                JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
                JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
                JUNJO_PROD_FRONTEND_URL="https://app.example.com",
                JUNJO_PROD_BACKEND_URL="https://api.example.com",
                # Missing: JUNJO_PROD_INGESTION_URL
            )

    def test_ingestion_url_must_have_protocol(self):
        """Test that ingestion URL must start with http:// or https://."""
        with pytest.raises(ValidationError, match="must start with http"):
            create_test_settings(
                JUNJO_ENV="production",
                JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
                JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
                JUNJO_PROD_FRONTEND_URL="https://app.example.com",
                JUNJO_PROD_BACKEND_URL="https://api.example.com",
                JUNJO_PROD_INGESTION_URL="ingestion.example.com",  # Missing protocol
            )

    def test_production_uses_ingestion_url(self):
        """Test that production uses the explicit ingestion URL."""
        settings = create_test_settings(
            JUNJO_ENV="production",
            JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
            JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
            JUNJO_PROD_FRONTEND_URL="https://app.example.com",
            JUNJO_PROD_BACKEND_URL="https://api.example.com",
            JUNJO_PROD_INGESTION_URL="https://ingestion.example.com",
        )
        assert settings.otlp_endpoint == "https://ingestion.example.com"

    def test_development_uses_localhost_default(self):
        """Test that development mode uses localhost default."""
        settings = create_test_settings(
            JUNJO_ENV="development",
            JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
            JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
        )
        assert settings.otlp_endpoint == "grpc://localhost:50051"


class TestSameDomainValidation:
    """Test same-domain validation for session cookies."""

    def test_same_domain_subdomain_subdomain(self):
        """Test valid: app.example.com + api.example.com."""
        settings = create_test_settings(
            JUNJO_ENV="production",
            JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
            JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
            JUNJO_PROD_FRONTEND_URL="https://app.example.com",
            JUNJO_PROD_BACKEND_URL="https://api.example.com",
            JUNJO_PROD_INGESTION_URL="https://ingestion.example.com",
        )
        # Should not raise
        assert settings.prod_frontend_url == "https://app.example.com"

    def test_same_domain_apex_subdomain(self):
        """Test valid: example.com + api.example.com."""
        settings = create_test_settings(
            JUNJO_ENV="production",
            JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
            JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
            JUNJO_PROD_FRONTEND_URL="https://example.com",
            JUNJO_PROD_BACKEND_URL="https://api.example.com",
            JUNJO_PROD_INGESTION_URL="https://ingestion.example.com",
        )
        # Should not raise
        assert settings.prod_backend_url == "https://api.example.com"

    def test_same_domain_subdomain_apex(self):
        """Test valid: app.example.com + example.com."""
        settings = create_test_settings(
            JUNJO_ENV="production",
            JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
            JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
            JUNJO_PROD_FRONTEND_URL="https://app.example.com",
            JUNJO_PROD_BACKEND_URL="https://example.com",
            JUNJO_PROD_INGESTION_URL="https://ingestion.example.com",
        )
        # Should not raise
        assert settings.prod_frontend_url == "https://app.example.com"

    def test_cross_domain_fails(self):
        """Test invalid: app.example.com + service.run.app."""
        with pytest.raises(ValidationError, match="must share the same registrable domain"):
            create_test_settings(
                JUNJO_ENV="production",
                JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
                JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
                JUNJO_PROD_FRONTEND_URL="https://app.example.com",
                JUNJO_PROD_BACKEND_URL="https://service.run.app",
                JUNJO_PROD_INGESTION_URL="https://ingestion.run.app",
            )

    def test_tldextract_handles_co_uk(self):
        """Test that tldextract handles .co.uk correctly."""
        settings = create_test_settings(
            JUNJO_ENV="production",
            JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
            JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
            JUNJO_PROD_FRONTEND_URL="https://app.example.co.uk",
            JUNJO_PROD_BACKEND_URL="https://api.example.co.uk",
            JUNJO_PROD_INGESTION_URL="https://ingestion.example.co.uk",
        )
        # Should not raise (tldextract knows .co.uk is a valid suffix)
        assert settings.prod_frontend_url == "https://app.example.co.uk"

    def test_tldextract_handles_gov_au(self):
        """Test that tldextract handles .gov.au correctly."""
        settings = create_test_settings(
            JUNJO_ENV="production",
            JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
            JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
            JUNJO_PROD_FRONTEND_URL="https://app.example.gov.au",
            JUNJO_PROD_BACKEND_URL="https://api.example.gov.au",
            JUNJO_PROD_INGESTION_URL="https://ingestion.example.gov.au",
        )
        # Should not raise
        assert settings.prod_backend_url == "https://api.example.gov.au"

    def test_cross_domain_co_uk_fails(self):
        """Test that cross-domain validation works with .co.uk TLDs."""
        with pytest.raises(ValidationError, match="must share the same registrable domain"):
            create_test_settings(
                JUNJO_ENV="production",
                JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
                JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
                JUNJO_PROD_FRONTEND_URL="https://app.example.co.uk",
                JUNJO_PROD_BACKEND_URL="https://api.different.co.uk",
                JUNJO_PROD_INGESTION_URL="https://ingestion.different.co.uk",
            )

    def test_different_subdomains_same_domain(self):
        """Test that different subdomains on same domain are valid."""
        settings = create_test_settings(
            JUNJO_ENV="production",
            JUNJO_SECURE_COOKIE_KEY=TEST_COOKIE_KEY,
            JUNJO_SESSION_SECRET=TEST_SESSION_SECRET,
            JUNJO_PROD_FRONTEND_URL="https://studio.example.com",
            JUNJO_PROD_BACKEND_URL="https://backend.example.com",
            JUNJO_PROD_INGESTION_URL="https://ingestion.example.com",
        )
        # Should not raise - both share example.com
        assert settings.prod_frontend_url == "https://studio.example.com"
