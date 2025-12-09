"""Admin endpoints for system operations."""

from fastapi import APIRouter, HTTPException, status
from loguru import logger
from pydantic import BaseModel, Field

from app.features.auth.dependencies import CurrentUser
from app.features.parquet_indexer.background_indexer import index_new_files
from app.features.span_ingestion.ingestion_client import IngestionClient

router = APIRouter(prefix="/admin", tags=["admin"])


class FlushWALResponse(BaseModel):
    """Response for WAL flush operation."""

    success: bool = Field(examples=[True])
    message: str = Field(examples=["WAL flush completed"])
    files_indexed: int = Field(default=0, examples=[1])


@router.post("/flush-wal", response_model=FlushWALResponse)
async def flush_wal(authenticated_user: CurrentUser) -> FlushWALResponse:
    """Trigger WAL flush to Parquet files and index new files. Requires authentication."""
    logger.info(f"WAL flush requested by user: {authenticated_user.email}")

    client = IngestionClient()
    await client.connect()
    try:
        success = await client.flush_wal()
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="WAL flush failed",
            )

        # Immediately index the new Parquet file(s) created by the flush
        files_indexed = await index_new_files()
        logger.info(f"Post-flush indexing completed: {files_indexed} files indexed")

        return FlushWALResponse(
            success=True,
            message=f"WAL flush completed, {files_indexed} file(s) indexed",
            files_indexed=files_indexed,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WAL flush error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    finally:
        await client.close()
