"""Common utilities.

Pattern from wt_api_v2 (using nanoid for short, unique IDs).
"""

from nanoid import generate as nanoid_generate

ID_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def generate_id(size: int = 22) -> str:
    """Generate a URL- and CLI-safe unique ID using nanoid.

    Args:
        size: Length of the ID (default 22 characters)

    Returns:
        A URL-safe, unique identifier

    Example:
        >>> generate_id(22)
        'V1StGXR8Z5jdHi6BmyT2Qa'
    """
    return nanoid_generate(ID_ALPHABET, size)
