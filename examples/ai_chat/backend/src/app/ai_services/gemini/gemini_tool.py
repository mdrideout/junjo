import os
from typing import TypeVar

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel

# Define a TypeVar bound to BaseModel for the schema request
T = TypeVar("T", bound=BaseModel)


class GeminiTool:
    """A tool for making requests to the Google Gemini LLM via the google genai library."""

    _prompt: str
    _model: str
    _client: genai.Client

    def __init__(self, prompt: str, model: str):
        """
        A tool that uses the Gemini AI model to generate content based on a prompt.

        Attributes:
            prompt (str): The prompt to send in the request to Gemini.
            model (str): The gemini model to use in the request

        Docs:
            Model Options: https://ai.google.dev/gemini-api/docs/models/gemini
            Model Examples: "gemini-2.0-flash", "gemini-2.0-flash-lite-001"

        Methods:
            text_request(): Sends a text request to the Gemini AI model.
            model_request(): Sends a request to the Gemini AI model and validates, returns a Pydantic model.
        """

        # Get the API Key from env file
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        # Create the gemini client
        self._client = genai.Client(api_key=gemini_api_key)
        self._prompt = prompt
        self._model = model

    async def text_request(self) -> str:
        """
        Sends a text request to the Gemini AI model.
        """
        response = await self._client.aio.models.generate_content(model=self._model, contents=self._prompt)

        text = response.text
        if text is None:
            logger.error(f"No text in response: {response}")
            raise ValueError("No text in response")

        return text.strip()

    async def schema_request(self, schema: type[T]) -> T:
        """
        Sends a request to the Gemini AI model and validates, returns a Pydantic model.

        Args:
            schema (Type[T]): (BaseModel bound) The Pydantic model class to validate against.

        Docs: https://ai.google.dev/gemini-api/docs/migrate#json_response
        """
        logger.info(f"Making schema request with prompt: {self._prompt}")

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=500, temperature=2, response_mime_type="application/json", response_schema=schema
            ),
        )
        logger.info(f"Raw response: {response}")

        schema_response = response.parsed
        if schema_response is None:
            logger.error(f"Parsed schema response is None: {response}")

        # Validate again using the provided model
        validated = schema.model_validate(schema_response)

        return validated
