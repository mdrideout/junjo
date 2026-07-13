from enum import StrEnum


class MessageDirective(StrEnum):
    """
    The directive for the LLM response to follow inferred from the user's message.
    """

    DATE_IDEA_RESEARCH = "DATE_IDEA_RESEARCH"
    WORK_RELATED_RESPONSE = "WORK_RELATED_RESPONSE"
    GENERAL_RESPONSE = "GENERAL_RESPONSE"
    IMAGE_RESPONSE = "IMAGE_RESPONSE"
