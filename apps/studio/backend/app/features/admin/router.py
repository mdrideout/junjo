"""Admin endpoints for system operations."""

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import BaseModel

from app.features.auth.dependencies import CurrentUser
from app.features.span_ingestion.ingestion_client import IngestionClient

router = APIRouter(prefix="/admin", tags=["admin"])


class FlushWALResponse(BaseModel):
    """Response for WAL flush operation."""

    success: bool
    message: str


@router.post("/flush-wal", response_model=FlushWALResponse)
async def flush_wal(authenticated_user: CurrentUser) -> FlushWALResponse:
    """Trigger WAL flush to Parquet files. Requires authentication."""
    logger.info(f"WAL flush requested by user: {authenticated_user.email}")

    client = IngestionClient()
    await client.connect()
    try:
        success = await client.flush_wal()
        if success:
            return FlushWALResponse(success=True, message="WAL flush completed")
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="WAL flush failed",
            )
    except Exception as e:
        logger.error(f"WAL flush error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    finally:
        await client.close()
