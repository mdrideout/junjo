

def create_joke_prompt(items: list[str]) -> str:
    """Prompt to create a joke based on personality traits."""

    # Create the prompt
    return f"""
Create a short joke based on the following items. You must incorporate all of the items into the joke:

Items: {items}

Output only a single definitive joke in under 250 words. Do not be conversational or include any additional information.

Do not include wrapping quotes or any special formatting characters. Just output the joke.
""".strip()
