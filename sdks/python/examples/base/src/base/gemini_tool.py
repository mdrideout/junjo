import os
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

# Define a TypeVar bound to BaseModel for the schema request
T = TypeVar("T", bound=BaseModel)

class GeminiTool:
    """A tool for making requests to the Google Gemini LLM via the google genai library.

    :param prompt: The prompt to send in the request to Gemini.
    :type prompt: str
    :param model: The gemini model to use in the request.
        See https://ai.google.dev/gemini-api/docs/models for available models.
        Examples: "gemini-2.5-flash", "gemini-2.5-flash-lite"
    :type model: str
    :raises ValueError: If GEMINI_API_KEY environment variable is not set

    **Methods:**

    - ``text_request()``: Sends a text request to the Gemini AI model.
    - ``schema_request(schema)``: Sends a request to the Gemini AI model and validates, returns a Pydantic model.
    """

    _prompt: str
    _model: str
    _client: genai.Client

    def __init__(self, prompt: str, model: str):

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
            print(f"No text in response: {response}")
            raise ValueError("No text in response")

        return text.strip()

    async def schema_request(self, schema: type[T]) -> T:
        """
        Sends a request to the Gemini AI model and validates, returns a Pydantic model.

        Args:
            schema (Type[T]): (BaseModel bound) The Pydantic model class to validate against.

        Docs: https://ai.google.dev/gemini-api/docs/migrate#json_response
        """
        print(f"Making schema request with prompt: {self._prompt}")

        # Extract JSON schema for better telemetry capture
        schema_dict = schema.model_json_schema()

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=8192,  # Increased to accommodate thinking + output tokens
                temperature=0.0,  # Low temperature for deterministic, consistent outputs
                response_mime_type="application/json",
                response_json_schema=schema_dict,  # Use dict for full telemetry capture
            ),
        )
        print(f"Raw response: {response}")

        # Check for MAX_TOKENS finish reason
        if response.candidates and str(response.candidates[0].finish_reason) == "FinishReason.MAX_TOKENS":
            raise ValueError(
                f"Response exceeded max_output_tokens. Increase the limit or simplify the schema. "
                f"Thoughts: {response.usage_metadata.thoughts_token_count if response.usage_metadata else 'N/A'}, "
                f"Total: {response.usage_metadata.total_token_count if response.usage_metadata else 'N/A'}"
            )

        schema_response = response.parsed
        if schema_response is None:
            print(f"Parsed schema response is None: {response}")
            raise ValueError(f"Failed to parse structured output. Response: {response.text}")

        # Validate again using the provided model
        validated = schema.model_validate(schema_response)

        return validated
