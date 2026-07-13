"""Common utilities.

Pattern from wt_api_v2 (using nanoid for short, unique IDs).
"""

from nanoid import generate as nanoid_generate


def generate_id(size: int = 22) -> str:
    """Generate a unique ID using nanoid.

    Args:
        size: Length of the ID (default 22 characters)

    Returns:
        A URL-safe, unique identifier

    Example:
        >>> generate_id(22)
        'V1StGXR8_Z5jdHi6B-myT'
    """
    return nanoid_generate(size=size)
