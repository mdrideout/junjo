

import asyncio

from loguru import logger

from app.ai_services.gemini.gemini_tool import GeminiTool
from app.db.models.chat_members.repository import ChatMembersRepository
from app.db.models.contact.repository import ContactRepository
from app.db.models.message.repository import MessageRepository
from app.db.models.message.schemas import MessageCreate, MessageRead
from app.workflows.message.prompt_gemini import message_response_prompt_gemini


async def create_message_response(message: MessageRead):
    """
    A workflow to create a message response to the received message,
    and save it to the database for future retrieval.
    """

    # Add an artificial 1 second delay
    await asyncio.sleep(1)

    # Get the non null participants of this chat from the database
    members = await ChatMembersRepository().read_by_chat_id(message.chat_id)
    logger.info(f"Members: {members}")

    # If no members, or length is 0, throw an exception
    if not members or len(members) == 0:
        raise Exception("No members found")

    # Get the first member (for now, in case there are more)
    member = members[0]
    member_contact_id = member.contact_id

    if not member_contact_id:
        raise Exception("No contact ID found")

    # Get this contact's information
    contact = await ContactRepository.read(member_contact_id)
    logger.info(f"Contact: {contact}")

    if not contact:
        raise Exception("No contact found")

    # Create the message response...
    # Construct the prompt
    prompt = message_response_prompt_gemini(message.message, contact.gender)

    # Create a request to gemini
    gemini_tool = GeminiTool(prompt=prompt, model="gemini-1.5-flash-8b-001")
    gemini_result = await gemini_tool.text_request()
    logger.info(f"Gemini result: {gemini_result}")

    # Create a message for the database
    message_create = MessageCreate(
        chat_id=message.chat_id,
        contact_id=member.contact_id,
        message=gemini_result
    )

    # Insert the message into the database
    await MessageRepository.create(message_create)

    return
