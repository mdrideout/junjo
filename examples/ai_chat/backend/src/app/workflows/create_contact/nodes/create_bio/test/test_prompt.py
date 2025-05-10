

def test_evaluate_bio_prompt(bio: str) -> str:
    """Prompt to create a user bio based on personality traits."""

    # Create the prompt
    return f"""
Your job is to evaluate whether the following bio conforms to the bio requirements.

This is the bio to evaluate:
{bio}

Requirements:
- Is a realistic social media profile bio
- Must incorporate all of the following elements
    - History
    - Hobbies and interests
    - Work (a specific job title and employer)
    - Family status (kids, spouse, single, divorced, etc.)
    - Recent vacations taken

Output only JSON according to the following schema:

{{
    "passed": boolean, // whether the bio passed the requirements
    "reason": string, // a short concise reason why the bio failed
}}
""".strip()
