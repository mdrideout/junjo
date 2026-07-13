

def create_fact_prompt(joke: str) -> str:
    """Prompt to create a fact based on the joke provided."""

    # Create the prompt
    return f"""
Create a short fact based on the following joke.

Joke: {joke}

Output only a single definitive fact in under 250 words. Do not be conversational or include any additional information.

Do not include wrapping quotes or any special formatting characters. Just output the fact.
""".strip()
