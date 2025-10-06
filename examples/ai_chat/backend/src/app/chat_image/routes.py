from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.util.get_image_file import get_image_file

chat_image_router = APIRouter(prefix="/api/chat-image")


@chat_image_router.get("/{chat_id}/{image_id}")
async def get_chat_image(chat_id: str, image_id: str) -> FileResponse:
    """
    Get the chat PNG for the given id.
    """
    folder = f"chat-images/{chat_id}"
    file_path = get_image_file(folder, image_id, "png")
    return FileResponse(path=file_path, media_type="image/png")
