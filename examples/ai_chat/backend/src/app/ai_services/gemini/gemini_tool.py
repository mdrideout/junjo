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

    @staticmethod
    def _safety_settings_off() -> list[types.SafetySetting]:
        """
        Turn off all adjustable Gemini safety filters.

        Note: The Gemini API still enforces non-adjustable protections (for example, child safety).
        """

        return [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.OFF,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.OFF,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.OFF,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.OFF,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
                threshold=types.HarmBlockThreshold.OFF,
            ),
        ]

    def _log_block_reason(self, response: object, *, context: str) -> None:
        """
        Best-effort logging for Gemini content blocks.

        Useful when the API returns no content or omits image parts due to safety / policy restrictions.
        """

        try:
            response_id = getattr(response, "response_id", None)
            model_version = getattr(response, "model_version", None)
            logger.warning(
                f"{context}: Gemini response blocked/empty (response_id={response_id}, model_version={model_version})"
            )

            prompt_feedback = getattr(response, "prompt_feedback", None)
            if prompt_feedback:
                logger.warning(
                    f"{context}: prompt_feedback.block_reason={getattr(prompt_feedback, 'block_reason', None)} "
                    f"message={getattr(prompt_feedback, 'block_reason_message', None)}"
                )
                for rating in getattr(prompt_feedback, "safety_ratings", []) or []:
                    logger.warning(
                        f"{context}: prompt safety_rating "
                        f"category={getattr(rating, 'category', None)} "
                        f"blocked={getattr(rating, 'blocked', None)} "
                        f"probability={getattr(rating, 'probability', None)} "
                        f"severity={getattr(rating, 'severity', None)}"
                    )

            candidates = getattr(response, "candidates", []) or []
            if candidates:
                candidate = candidates[0]
                logger.warning(
                    f"{context}: candidate.finish_reason={getattr(candidate, 'finish_reason', None)} "
                    f"finish_message={getattr(candidate, 'finish_message', None)}"
                )
                for rating in getattr(candidate, "safety_ratings", []) or []:
                    logger.warning(
                        f"{context}: candidate safety_rating "
                        f"category={getattr(rating, 'category', None)} "
                        f"blocked={getattr(rating, 'blocked', None)} "
                        f"probability={getattr(rating, 'probability', None)} "
                        f"severity={getattr(rating, 'severity', None)}"
                    )

            # If available, log raw prompt feedback / safety ratings from the SDK's HTTP response.
            # This helps when the client library doesn't fully map newer enum values (e.g. IMAGE_OTHER).
            sdk_http_response = getattr(response, "sdk_http_response", None)
            if sdk_http_response is not None:
                raw = getattr(sdk_http_response, "json", None)
                if isinstance(raw, dict):
                    prompt_feedback_raw = raw.get("promptFeedback") or raw.get("prompt_feedback")
                    if isinstance(prompt_feedback_raw, dict):
                        logger.warning(
                            f"{context}: raw.prompt_feedback.block_reason="
                            f"{prompt_feedback_raw.get('blockReason') or prompt_feedback_raw.get('block_reason')} "
                            f"message={prompt_feedback_raw.get('blockReasonMessage') or prompt_feedback_raw.get('block_reason_message')}"
                        )
                        for rating in (
                            prompt_feedback_raw.get("safetyRatings")
                            or prompt_feedback_raw.get("safety_ratings")
                            or []
                        ):
                            logger.warning(
                                f"{context}: raw.prompt safety_rating "
                                f"category={rating.get('category')} "
                                f"blocked={rating.get('blocked')} "
                                f"probability={rating.get('probability')} "
                                f"severity={rating.get('severity')}"
                            )

                    candidates_raw = raw.get("candidates") or []
                    if candidates_raw:
                        candidate_raw = candidates_raw[0]
                        logger.warning(
                            f"{context}: raw.candidate.finish_reason="
                            f"{candidate_raw.get('finishReason') or candidate_raw.get('finish_reason')} "
                            f"finish_message={candidate_raw.get('finishMessage') or candidate_raw.get('finish_message')}"
                        )
                        for rating in candidate_raw.get("safetyRatings") or candidate_raw.get("safety_ratings") or []:
                            logger.warning(
                                f"{context}: raw.candidate safety_rating "
                                f"category={rating.get('category')} "
                                f"blocked={rating.get('blocked')} "
                                f"probability={rating.get('probability')} "
                                f"severity={rating.get('severity')}"
                            )
        except Exception:
            logger.exception(f"{context}: failed to log Gemini block reason")

    async def text_request(self) -> str:
        """
        Sends a text request to the Gemini AI model.
        """
        logger.debug(f"Making text request with model: {self._model}, prompt: {self._prompt}")
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._prompt,
            config=types.GenerateContentConfig(safety_settings=self._safety_settings_off()),
        )

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
                max_output_tokens=500,
                temperature=2,
                response_mime_type="application/json",
                response_schema=schema,
                safety_settings=self._safety_settings_off(),
            ),
        )
        logger.info(f"Raw response: {response}")

        schema_response = response.parsed
        if schema_response is None:
            logger.error(f"Parsed schema response is None: {response}")

        # Validate again using the provided model
        validated = schema.model_validate(schema_response)

        return validated

    async def gemini_image_request(self) -> bytes:
        """
        Sends a request to the Gemini AI model for an image.
        """
        bytes = None

        logger.debug(f"Making gemini_image_request with model: {self._model}, prompt: {self._prompt}")
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._prompt,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                safety_settings=self._safety_settings_off(),
            ),
        )

        if not response.candidates:
            self._log_block_reason(response, context="gemini_image_request:no_candidates")
            logger.error(f"No candidates in response: {response}")
            raise ValueError("No candidates in response")

        if not response.candidates[0].content:
            self._log_block_reason(response, context="gemini_image_request:no_content")
            logger.error(f"No content in response: {response}")
            raise ValueError("No content in response")

        if not response.candidates[0].content.parts:
            self._log_block_reason(response, context="gemini_image_request:no_parts")
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
            self._log_block_reason(response, context="gemini_image_request:no_image_bytes")
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
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=[self._prompt, image],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                safety_settings=self._safety_settings_off(),
            ),
        )

        if not response.candidates:
            self._log_block_reason(response, context="gemini_image_edit_request:no_candidates")
            logger.error(f"No candidates in response: {response}")
            raise ValueError("No candidates in response")

        if not response.candidates[0].content:
            # If prohibited content
            if response.candidates[0].finish_reason is not None:
                self._log_block_reason(response, context="gemini_image_edit_request:blocked")
                logger.warning(
                    f"Prohibited content detected in response.Finish Reason: {response.candidates[0].finish_reason}"
                )
                return None, str(response.candidates[0].finish_reason)

            self._log_block_reason(response, context="gemini_image_edit_request:no_content")
            logger.error(f"No content in response: {response}")
            raise ValueError("No content in response")

        if not response.candidates[0].content.parts:
            self._log_block_reason(response, context="gemini_image_edit_request:no_parts")
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
            self._log_block_reason(response, context="gemini_image_edit_request:no_image_bytes")
            logger.error(f"No image bytes in response: {response}")

        return bytes_response, text_response
