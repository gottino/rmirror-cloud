"""OCR service using Claude Vision API for handwritten text extraction."""

import base64
from typing import BinaryIO

import anthropic

from app.config import get_settings

settings = get_settings()


class OCRService:
    """OCR service for extracting handwritten text using Claude Vision."""

    def __init__(self, api_key: str | None = None):
        """
        Initialize OCR service.

        Args:
            api_key: Anthropic API key (uses CLAUDE_API_KEY from env if not provided)
        """
        # For now, get from environment
        # TODO: Add CLAUDE_API_KEY to settings
        self.client = anthropic.Anthropic(api_key=api_key)

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
        """
        # Encode PDF to base64
        pdf_base64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

        # Default prompt for handwriting OCR
        if prompt is None:
            prompt = (
                "Please extract all handwritten text from this image. "
                "Return only the text content, preserving the structure and formatting as much as possible. "
                "If there are multiple sections or paragraphs, separate them with blank lines."
            )

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
            return message.content[0].text

        return ""

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
        """
        # Encode image to base64
        image_base64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        # Default prompt
        if prompt is None:
            prompt = (
                "Please extract all handwritten text from this image. "
                "Return only the text content, preserving the structure and formatting."
            )

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
            return message.content[0].text

        return ""
