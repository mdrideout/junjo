#!/usr/bin/env python3
"""
Export OpenAPI schema from FastAPI app without running the server.

This script imports the FastAPI app directly and calls app.openapi()
to generate the OpenAPI specification. This approach:
- Does NOT require the server to be running
- Works in CI/CD pipelines
- Follows FastAPI best practices

Usage:
    python scripts/export_openapi_schema.py

Output:
    Creates openapi.json in the backend directory
"""

import json
import sys
from pathlib import Path

from loguru import logger


def export_openapi_schema(output_path: Path) -> None:
    """Export OpenAPI schema from FastAPI app.

    Args:
        output_path: Path to output JSON file
    """
    try:
        # Import the FastAPI app
        # NOTE: This import may trigger database initialization, logging setup, etc.
        logger.info("Importing FastAPI app...")
        from app.main import app

        # Generate OpenAPI schema
        logger.info("Generating OpenAPI schema...")
        schema = app.openapi()

        # Save to file
        logger.info(f"Saving schema to {output_path}")
        with open(output_path, "w") as f:
            json.dump(schema, f, indent=2)

        # Print summary
        logger.success(f"OpenAPI schema exported to {output_path}")
        logger.info("-" * 60)
        logger.info(f"OpenAPI version: {schema.get('openapi', 'unknown')}")
        logger.info(f"API title: {schema.get('info', {}).get('title', 'unknown')}")
        logger.info(f"API version: {schema.get('info', {}).get('version', 'unknown')}")
        logger.info(f"Endpoints: {len(schema.get('paths', {}))}")
        logger.info(f"Schemas: {len(schema.get('components', {}).get('schemas', {}))}")
        logger.info("-" * 60)

    except ImportError as e:
        logger.error(f"Failed to import FastAPI app: {e}")
        logger.error("Make sure you're running from the backend directory with dependencies installed")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


def main():
    # Output file in backend root directory
    backend_dir = Path(__file__).parent.parent
    output_path = backend_dir / "openapi.json"

    logger.info("=" * 60)
    logger.info("FastAPI OpenAPI Schema Exporter")
    logger.info("=" * 60)

    export_openapi_schema(output_path)


if __name__ == "__main__":
    main()
