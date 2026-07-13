from pathlib import Path

from fastapi import HTTPException
from loguru import logger


def get_image_file(project_root_folder: str, file_name: str, file_ext: str) -> Path:
    """
    Locate an image under <project_root>/<project_root_folder>/<file_name>.<file_ext>.
    Raises HTTPException(404) if not found.
    """
    current_file = Path(__file__)
    # climb back up to project root (same as in save_image_file)
    project_root = current_file.parent.parent.parent.parent

    images_dir = project_root / project_root_folder
    file_path = images_dir / f"{file_name}.{file_ext}"

    if not file_path.exists():
        logger.error(f"Image not found at {file_path}")
        raise HTTPException(status_code=404, detail="Image not found")

    return file_path
