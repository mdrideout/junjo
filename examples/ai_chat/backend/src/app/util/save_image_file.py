from pathlib import Path

from loguru import logger


def save_image_file(data: bytes, project_root_folder: str, file_name: str, file_ext: str) -> str:
    """
    Save image data to a file.

    Args:
        data (bytes): The image data to save.
        project_root_folder (str): The root folder of the project.
        file_name (str): The name of the file to save the image as.
        file_ext (str): The file extension (e.g., 'png', 'jpg').

    Returns:
        str: The path to the saved image file.
    """
    # Get the current file's path
    current_file = Path(__file__)

    # Get the project root (adjust the number of parent directories as needed)
    project_root = current_file.parent.parent.parent.parent  # Adjust this level if necessary

    # Create the avatars directory if it doesn't exist
    avatars_dir = project_root / project_root_folder
    avatars_dir.mkdir(parents=True, exist_ok=True)

    # Construct the absolute path to the avatar file
    final_file_path = avatars_dir / f"{file_name}.{file_ext}"

    with open(final_file_path, "wb") as f:
        f.write(data)

    # Log the file path
    logger.info(f"Image saved to: {final_file_path}")

    return str(final_file_path)
