from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.util.get_image_file import get_image_file

avatar_router = APIRouter(prefix="/api/avatar")


@avatar_router.get("/{avatar_id}")
async def get_contact_avatar(avatar_id: str) -> FileResponse:
    """
    Get the avatar PNG for the given id.
    """
    # adjust folder name if you used something different in save_image_file
    file_path = get_image_file("avatars", avatar_id, "png")
    return FileResponse(path=file_path, media_type="image/png")
