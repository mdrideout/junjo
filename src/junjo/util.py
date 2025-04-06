from nanoid import generate


def generate_safe_id(size: int = 21) -> str:
    """
    Generates a random ID using a safe alphabet for Mermaid diagrams.

    Args:
        size: The length of the ID to generate.

    Returns:
        A random ID string.
    """
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return generate(alphabet, size)
