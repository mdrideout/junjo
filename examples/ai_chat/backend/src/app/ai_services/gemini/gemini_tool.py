import os
from io import BytesIO
from typing import TypeVar

from google import genai
from google.genai import types
from loguru import logger
from PIL import Image
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
        logger.debug(f"Making text request with model: {self._model}, prompt: {self._prompt}")
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

        logger.debug(f"Making schema request with model: {self._model}, prompt: {self._prompt}, schema: {schema}")
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


    async def imagen_3_request(self) -> bytes:
        """
        Sends a request to the Gemini AI model for an image.
        """
        bytes = None

        logger.debug(f"Making imagen_3_request with model: {self._model}, prompt: {self._prompt}")
        response = await self._client.aio.models.generate_images(
            model=self._model,
            prompt=self._prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1, aspect_ratio="1:1", person_generation=types.PersonGeneration.ALLOW_ADULT
            ),
        )

        if not response.generated_images:
            logger.error(f"No generated images in response: {response}")
            raise ValueError("No generated images in response")

        for generated_image in response.generated_images:
            if not generated_image.image:
                logger.error(f"No image in generated image: {generated_image}")
                raise ValueError("No image in generated image")

            # Get the image bytes
            bytes = generated_image.image.image_bytes

        if not bytes:
            logger.error(f"No image bytes in generated image: {generated_image}")
            raise ValueError("No image bytes in generated image")

        return bytes

    async def gemini_image_request(self) -> bytes:
        """
        Sends a request to the Gemini AI model for an image.
        """
        bytes = None

        logger.debug(f"Making gemini_image_request with model: {self._model}, prompt: {self._prompt}")
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._prompt,
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )

        if not response.candidates:
            logger.error(f"No candidates in response: {response}")
            raise ValueError("No candidates in response")

        if not response.candidates[0].content:
            logger.error(f"No content in response: {response}")
            raise ValueError("No content in response")

        if not response.candidates[0].content.parts:
            logger.error(f"No parts in response: {response}")
            raise ValueError("No parts in response")

        for part in response.candidates[0].content.parts:
            if part.text is not None:
                # Log the text part
                logger.info(f"Gemini image generation text: {part.text}")

            if not part.inline_data:
                # Skip this part if it doesn't contain inline data
                continue

            # Get the image bytes from the inline data
            bytes = part.inline_data.data

        if not bytes:
            logger.error(f"No image bytes in part: {part}")
            raise ValueError("No image bytes in part")

        return bytes

    async def gemini_image_edit_request(self, image_bytes: bytes) -> tuple[bytes | None, str | None]:
        """
        Sends a request to the Gemini AI model for an image.
        """

        bytes_response = None
        text_response = None

        image = Image.open(BytesIO(image_bytes))

        logger.debug(f"Making gemini_image_edit_request with model: {self._model}, prompt: {self._prompt}")
        response = await self._client.aio.models.generate_content(model=self._model, contents=[self._prompt, image])

        if not response.candidates:
            logger.error(f"No candidates in response: {response}")
            raise ValueError("No candidates in response")

        if not response.candidates[0].content:
            logger.error(f"No content in response: {response}")
            raise ValueError("No content in response")

        if not response.candidates[0].content.parts:
            logger.error(f"No parts in response: {response}")
            raise ValueError("No parts in response")

        for part in response.candidates[0].content.parts:
            if part.text is not None:
                # Log the text part
                logger.info(f"gemini_image_edit_request text: {part.text}")
                text_response = part.text

            if part.inline_data:
                # Get the image bytes from the inline data
                bytes_response = part.inline_data.data

        if not bytes_response:
            logger.error(f"No image bytes in response: {response}")

        return bytes_response, text_response
