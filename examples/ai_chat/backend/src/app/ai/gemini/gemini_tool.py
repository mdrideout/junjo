import os
from typing import Type, TypeVar

from google import genai
from google.genai import types
from loguru import logger
from pydantic import BaseModel

# Define a TypeVar bound to BaseModel
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

      #Get the API Key from env file
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
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._prompt
        )

        text = response.text
        if text is None:
            logger.error(f"No text in response: {response}")
            raise ValueError("No text in response")

        return text.strip()



    # async def gemini_model_request(
    #     self, model_class: Type[T], json_only: bool = False
    # ) -> T:
    #     """
    #     Sends a JSON request to the Gemini AI model.
    #     Validates the JSON output against the provided Pydantic model and returns an instance of that model.

    #     Args:
    #         model_class (Type[T]): The Pydantic model class to validate against.
    #         json_only (bool): Whether to validate the JSON output only (default: False).
    #             If True, the model will not be provided to repsonse_schema in the generation_config.
    #             Sometimes there are bugs where the model cannot be validated, so this is a workaround.

    #     Returns:
    #         T: An instance of the provided Pydantic model.

    #     Raises:
    #         ValueError: If the JSON cannot be decoded or validation fails.
    #     """

    #     # TODO: JSON Response mode: https://ai.google.dev/gemini-api/docs/migrate#json_response
    #     # Accepts Pydantic model and provides response.parsed
    #     # Create config for consistent model outputs
    #     config = types.GenerateContentConfig(
    #         temperature=0,
    #         response_mime_type= 'application/json',
    #         response_schema=model_class
    #     )

    #     # Generate content and stripe whitespace
    #     try:
    #         response = await self.model.generate_content_async(
    #             self.prompt,
    #             generation_config=genai.GenerationConfig(
    #                 temperature=0,
    #                 response_mime_type="application/json",
    #                 response_schema=model_class if not json_only else None,
    #             ),
    #         )

    #     except Exception as e:
    #         logger.error(f"Error generating content: {e}")
    #         raise

    #     # Strip whitespace
    #     text = response.text.strip()
    #     logger.info(f"Model Request Response: {text}")

    #     # Convert the JSON string to JSON object
    #     try:
    #         # Parse and validate the JSON string directly using model_validate_json
    #         model_instance = model_class.model_validate_json(text)
    #         return model_instance

    #     except json.JSONDecodeError as e:
    #         logger.error(f"Error decoding JSON: {e}")
    #         logger.info(f"Raw JSON string: {text}")
    #         raise ValueError(f"Error decoding JSON into {model_class.__name__} model.")

    #     except Exception as e:
    #         logger.error(f"Validation error: {e}\nReceived JSON: {text}.")
    #         raise