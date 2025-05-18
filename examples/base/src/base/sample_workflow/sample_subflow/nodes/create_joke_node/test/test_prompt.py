

def test_evaluate_joke_prompt(joke: str, items: list[str]) -> str:
    """Prompt to create a user joke based on personality traits."""

    # Create the prompt
    return f"""
Your job is to evaluate whether the following joke conforms to the joke requirements.

This is the joke to evaluate:
=== JOKE START ===
{joke}
=== JOKE END ===

Requirements:
- There must be only one joke in the response
- The joke must be funny.
- On a scale of 1 (very bad) to 10 (worthy of an award), the joke must be a perfect 10.
- The joke must incorporate all of the items
- There is no conversational response, just the joke.
- There are no wrapping quotes or any special formatting characters, only the joke.

Items:
{", ".join(items)}

Be harsh in your evaluation. If the joke is not funny enough, or does not incorporate all of the items, or is not a joke
then it fails to pass the requirements.

Output only JSON according to the following schema:

{{
    "passed": boolean, // whether the joke passed the requirements
    "reason": string, // a short concise reason why the joke failed to pass the requirements
}}
""".strip()
