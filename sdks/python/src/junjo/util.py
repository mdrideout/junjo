from nanoid import generate


def generate_safe_id(size: int = 21) -> str:
    """
    Generate a random identifier using an alphabet that remains safe for
    Mermaid diagrams.

    :param size: The length of the identifier to generate.
    :type size: int
    :returns: A random identifier string.
    :rtype: str
    """
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return generate(alphabet, size)
