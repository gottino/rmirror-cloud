"""OCR service using Google Gemini Vision API for handwritten text extraction."""

import asyncio
import logging
import re
import time

from google import genai
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_OCR_PROMPT_RULES = (
    "Rules:\n"
    "- Preserve the EXACT layout: line breaks, indentation, and spatial hierarchy as written\n"
    "- Each new line of handwriting = a new line in output\n"
    "- Bullet points (dots, dashes, or filled circles at left margin): use `- ` (dash + space)\n"
    "- Indented/nested lines below a bullet: indent with 2 spaces per level and use `- `\n"
    "- Lines starting with ↳ or → arrows: just indent them (no extra dash, the arrow is the marker)\n"
    "- Checkboxes: use - [ ] (unchecked) or - [x] (checked) — these are square boxes □/☑\n"
    "- Arrows within text: use → ← ↑ ↓ for straight arrows, ↳ for curved/continuation arrows\n"
    "- Underlined text = headings (use ## or ###)\n"
    "- Dates are dd-mm-yyyy format (European). If a date appears (often right side of page), "
    "start with **Date: dd-mm-yyyy** followed by ---\n"
    "- Output clean Markdown, no explanations, no code fences (no ```)\n\n"
    "Example — if handwriting shows:\n"
    "  • Topic A → details\n"
    "  • Topic B\n"
    "      ↳ sub-point 1\n"
    "      ↳ sub-point 2\n\n"
    "Output:\n"
    "- Topic A → details\n"
    "- Topic B\n"
    "  ↳ sub-point 1\n"
    "  ↳ sub-point 2"
)


def build_ocr_prompt(language_hint: str) -> str:
    """Build the OCR prompt.

    Args:
        language_hint: Languages the handwriting is expected in (setting
            OCR_LANGUAGE_HINT, e.g. "German and English"). Empty means any
            language, and the prompt names none.
    """
    hint = language_hint.strip()
    if hint:
        language = f"The content is written in {hint}.\n\n"
    else:
        language = (
            "Keep each word in the language it is written in; do not translate.\n\n"
        )
    return "Transcribe all handwritten text from this page. " + language + _OCR_PROMPT_RULES


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
        self.prompt = build_ocr_prompt(settings.ocr_language_hint)
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

        # The Gemini SDK call is synchronous; run it on a worker thread so a
        # multi-second OCR call does not stall the event loop.
        return await asyncio.to_thread(
            self._call_vision_api,
            content_part=types.Part.from_bytes(
                data=pdf_bytes, mime_type="application/pdf"
            ),
            prompt=prompt or self.prompt,
            input_bytes=len(pdf_bytes),
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

            # Strip markdown code fences that Gemini sometimes wraps output in
            extracted_text = re.sub(r'^```\w*\n?', '', extracted_text)
            extracted_text = re.sub(r'\n?```$', '', extracted_text)

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
