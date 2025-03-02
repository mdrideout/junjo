def contact_create_prompt_gemini(schema: str) -> str:
    return f"""
Create an insane AI profile for a dating app game.
The intent is to have a dating partner with an intense personality to chat with.

Examples: sports enthusiast, hunter, artist, professional, religious, etc.

They should still be realistic. Don't be too silly.

These profiles are generated on demand. Make sure what you generate is unlike previous ones.
I need diverse American profiles from all over the country

Steps:
- Select a random state
- Select a random city in that state
- Generate a random first name
- Generate a random last name
- Complete the remaining fields.

Adhere to the following schema for field limitations:
{schema}
""".strip()
