from app.util.get_image_file import get_image_file


def get_image_bytes(project_root_folder: str, file_name: str, file_ext: str) -> bytes:
    """
    Locate an image under <project_root>/<project_root_folder>/<file_name>.<file_ext>
    and return its content as bytes.
    """
    file_path = get_image_file(project_root_folder, file_name, file_ext)
    with open(file_path, "rb") as f:
        return f.read()
