from app.db.models.message.schemas import MessageRead


def image_inspiration_prompt(
    conversation_history: list[MessageRead],
) -> str:
    """Creates an image prompt to inspire the image that will be generated."""

    # Create the prompt
    return f"""
You are in a chat on a mobile phone and coming up with a description of a good photo to respond with.
You can take a new picture, selfie, or access your old photos in your gallery to send.

The chat history is as follows:

{conversation_history}

# Output Instructions
Output a description of the photo you're sending in under 50 words.
Be realistic and mirror what people would actually send in this situation.
This is a prompt that will be sent to a photo generation model.

Include the following with the prompt:
- That it should be ultra-realistic
- the device used to take the photo
- the location of the photo
- the time of day
- the weather
- the set and setting of the photo
- "Aspect Ratio: 1:1 square"
- "The person in the provided image is the basis for this new photo, and is the person sending the message."

Do not include any additional information.
Do not be conversational, just output a single definitive photo generation prompt.
""".strip()
