"""OCR service using Claude Vision API for handwritten text extraction."""

import base64
import logging
from typing import BinaryIO

import anthropic

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class OCRService:
    """OCR service for extracting handwritten text using Claude Vision."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize OCR service.

        Args:
            api_key: Anthropic API key. If not provided, uses CLAUDE_API_KEY from settings.

        Raises:
            ValueError: If no API key is provided and not in settings
        """
        # Use provided API key or fall back to settings
        api_key = api_key or settings.claude_api_key

        if not api_key:
            raise ValueError(
                "Claude API key required. Set CLAUDE_API_KEY environment variable "
                "or provide api_key parameter."
            )

        self.client = anthropic.Anthropic(api_key=api_key)
        logger.info("Initialized OCR service with Claude API")

    async def extract_text_from_pdf(
        self, pdf_bytes: bytes, prompt: str | None = None
    ) -> str:
        """
        Extract handwritten text from PDF using Claude Vision.

        Args:
            pdf_bytes: PDF content as bytes
            prompt: Custom prompt (uses default if not provided)

        Returns:
            Extracted text

        Raises:
            Exception: If Claude API call fails
        """
        logger.info(f"Extracting text from PDF ({len(pdf_bytes)} bytes)")

        # Encode PDF to base64
        pdf_base64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

        # Default prompt for handwriting OCR
        if prompt is None:
            prompt = (
                "Please extract all handwritten text from this image. "
                "Return only the text content, preserving the structure and formatting as much as possible. "
                "If there are multiple sections or paragraphs, separate them with blank lines."
            )

        try:
            # Call Claude Vision API
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",  # Latest Claude with vision
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
            )

            # Extract text from response
            if message.content and len(message.content) > 0:
                extracted_text = message.content[0].text
                logger.info(f"Successfully extracted {len(extracted_text)} characters")
                return extracted_text

            logger.warning("Claude API returned empty response")
            return ""

        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            raise

    async def extract_text_from_image(
        self, image_bytes: bytes, media_type: str = "image/png", prompt: str | None = None
    ) -> str:
        """
        Extract handwritten text from image using Claude Vision.

        Args:
            image_bytes: Image content as bytes
            media_type: MIME type (image/png, image/jpeg, etc.)
            prompt: Custom prompt

        Returns:
            Extracted text

        Raises:
            Exception: If Claude API call fails
        """
        logger.info(f"Extracting text from image ({media_type}, {len(image_bytes)} bytes)")

        # Encode image to base64
        image_base64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        # Default prompt
        if prompt is None:
            prompt = (
                "Please extract all handwritten text from this image. "
                "Return only the text content, preserving the structure and formatting."
            )

        try:
            # Call Claude Vision API
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_base64,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
            )

            # Extract text from response
            if message.content and len(message.content) > 0:
                extracted_text = message.content[0].text
                logger.info(f"Successfully extracted {len(extracted_text)} characters")
                return extracted_text

            logger.warning("Claude API returned empty response")
            return ""

        except Exception as e:
            logger.error(f"Failed to extract text from image: {e}")
            raise
