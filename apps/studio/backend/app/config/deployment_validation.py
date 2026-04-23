"""Deployment configuration validation and startup logging."""

from urllib.parse import urlparse

import tldextract
from loguru import logger

from app.config.settings import settings


def log_deployment_configuration() -> None:
    """Log deployment configuration during application startup.

    Displays production/development mode with relevant URLs and security settings.
    Called from main.py lifespan function.
    """
    logger.info("-" * 80)

    if settings.junjo_env == "production":
        _log_production_config()
    else:
        _log_development_config()

    logger.info("-" * 80)


def _log_production_config() -> None:
    """Log production mode configuration."""
    logger.info("🔒 PRODUCTION MODE")
    logger.info("")

    # URLs are already validated by Pydantic (will raise ValueError if missing)
    # Just display configuration
    logger.info(f"Frontend URL:   {settings.prod_frontend_url}")
    logger.info(f"Backend URL:    {settings.prod_backend_url}")
    logger.info(f"Ingestion URL:  {settings.prod_ingestion_url}")
    logger.info("")

    # Display CORS configuration
    logger.info(f"CORS Origins: {', '.join(settings.cors_origins)}")

    # Show if CORS was auto-derived or explicitly set
    if settings.prod_frontend_url in settings.cors_origins and len(settings.cors_origins) == 1:
        logger.info("  → CORS auto-derived from frontend URL")
    else:
        logger.info("  → CORS explicitly configured")

    logger.info("")

    # Same-domain validation already done by Pydantic model validator
    # Just confirm it passed
    frontend_extract = tldextract.extract(urlparse(settings.prod_frontend_url).netloc)
    registrable_domain = f"{frontend_extract.domain}.{frontend_extract.suffix}"

    logger.info(f"✅ Same-domain validated: {registrable_domain}")
    logger.info("✅ Session cookies: Encrypted (AES-256) + Signed (HMAC)")
    logger.info("✅ HTTPS-only cookies enabled")
    logger.info("✅ CSRF protection: SameSite=Strict")
    logger.info("")
    logger.info("⚠️  DEPLOYMENT CHECKLIST:")
    logger.info("   □ Frontend accessible at configured URL")
    logger.info("   □ Backend accessible at configured URL")
    logger.info("   □ Ingestion service accessible at configured URL")
    logger.info("   □ Reverse proxy routes ingestion traffic to port 50051")
    logger.info("   □ SSL certificates valid for all domains")


def _log_development_config() -> None:
    """Log development mode configuration."""
    logger.info("🔧 DEVELOPMENT MODE")
    logger.info("")
    logger.info("⚠️  HTTPS-only cookies: DISABLED (development only)")
    logger.info("✅ Session cookies: Encrypted (AES-256) + Signed (HMAC)")
    logger.info("✅ CSRF protection: SameSite=Strict")
    logger.info("")
    logger.info(f"Frontend (development build): {settings.dev_frontend_origin}")
    logger.info(f"Frontend (production build):  {settings.prod_frontend_origin}")
    logger.info(f"Backend:  {settings.dev_backend_url}")
    logger.info(f"OTLP:     {settings.dev_otlp_endpoint}")
