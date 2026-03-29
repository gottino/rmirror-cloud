"""OCR service using Google Gemini Vision API for handwritten text extraction."""

import logging
import time

from google import genai
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

OCR_PROMPT = (
    "Transcribe all handwritten text from this page. "
    "The content is mixed German and English.\n\n"
    "Rules:\n"
    "- Preserve the EXACT layout: line breaks, indentation, and spatial hierarchy as written\n"
    "- Each new line of handwriting = a new line in output\n"
    "- Indented text stays indented (use 2-space increments)\n"
    "- Bullet points: use - (dash)\n"
    "- Checkboxes: use - [ ] (unchecked) or - [x] (checked) — these are square boxes □/☑\n"
    "- Arrows: use → ← ↑ ↓ for straight arrows, ↳ for curved/continuation arrows\n"
    "- Underlined text = headings (use ## or ###)\n"
    "- Dates are dd-mm-yyyy format (European). If a date appears (often right side of page), "
    "start with **Date: dd-mm-yyyy** followed by ---\n"
    "- Output clean Markdown, no explanations"
)


class OCRService:
    """OCR service for extracting handwritten text using Google Gemini Vision."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize OCR service.

        Args:
            api_key: Google AI API key. If not provided, uses GOOGLE_AI_API_KEY from settings.

        Raises:
            ValueError: If no API key is provided and not in settings
        """
        api_key = api_key or settings.google_ai_api_key

        if not api_key:
            raise ValueError(
                "Google AI API key required. Set GOOGLE_AI_API_KEY environment variable "
                "or provide api_key parameter."
            )

        self.client = genai.Client(api_key=api_key)
        self.model = settings.ocr_model
        logger.info("Initialized OCR service with model=%s", self.model)

    async def extract_text_from_pdf(
        self, pdf_bytes: bytes, prompt: str | None = None
    ) -> str:
        """
        Extract handwritten text from PDF using Gemini Vision.

        Args:
            pdf_bytes: PDF content as bytes
            prompt: Custom prompt (uses default if not provided)

        Returns:
            Extracted text

        Raises:
            Exception: If Gemini API call fails
        """
        logger.info(f"Extracting text from PDF ({len(pdf_bytes)} bytes)")

        return self._call_vision_api(
            content_part=types.Part.from_bytes(
                data=pdf_bytes, mime_type="application/pdf"
            ),
            prompt=prompt or OCR_PROMPT,
            input_bytes=len(pdf_bytes),
        )

    async def extract_text_from_image(
        self, image_bytes: bytes, media_type: str = "image/png", prompt: str | None = None
    ) -> str:
        """
        Extract handwritten text from image using Gemini Vision.

        Args:
            image_bytes: Image content as bytes
            media_type: MIME type (image/png, image/jpeg, etc.)
            prompt: Custom prompt

        Returns:
            Extracted text

        Raises:
            Exception: If Gemini API call fails
        """
        logger.info(f"Extracting text from image ({media_type}, {len(image_bytes)} bytes)")

        return self._call_vision_api(
            content_part=types.Part.from_bytes(
                data=image_bytes, mime_type=media_type
            ),
            prompt=prompt or OCR_PROMPT,
            input_bytes=len(image_bytes),
        )

    def _call_vision_api(self, content_part: types.Part, prompt: str, input_bytes: int) -> str:
        """Call Gemini Vision API with the given content part and prompt."""
        start = time.monotonic()
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[content_part, prompt],
            )

            duration_ms = round((time.monotonic() - start) * 1000)

            input_tokens = 0
            output_tokens = 0
            if response.usage_metadata:
                input_tokens = response.usage_metadata.prompt_token_count or 0
                output_tokens = response.usage_metadata.candidates_token_count or 0

            extracted_text = response.text or ""

            if extracted_text:
                logger.info(
                    "OCR completed: %d chars in %dms",
                    len(extracted_text),
                    duration_ms,
                    extra={
                        "event": "ocr.done",
                        "duration_ms": duration_ms,
                        "input_bytes": input_bytes,
                        "output_chars": len(extracted_text),
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "model": self.model,
                    },
                )
            else:
                logger.warning("Gemini API returned empty response")

            return extracted_text

        except Exception as e:
            duration_ms = round((time.monotonic() - start) * 1000)
            logger.error(
                "OCR failed after %dms: %s",
                duration_ms,
                e,
                extra={
                    "event": "ocr.fail",
                    "duration_ms": duration_ms,
                    "input_bytes": input_bytes,
                    "error": str(e),
                },
            )
            raise
