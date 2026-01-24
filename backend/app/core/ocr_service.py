"""OCR service using Claude Vision API for handwritten text extraction."""

import base64
import logging

import anthropic
import httpx

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

        # Create httpx client with SSL verification disabled for corporate networks
        # TODO: In production, configure proper certificate trust instead
        http_client = httpx.Client(verify=False)

        self.client = anthropic.Anthropic(api_key=api_key, http_client=http_client)
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
                "Please transcribe all handwritten text from this image in Markdown format.\n\n"
                "Instructions:\n"
                "- Extract ALL visible handwritten text, including notes, arrows, symbols, and annotations\n"
                "- Format the output as clean Markdown with proper structure\n"
                "- Use ## for main headings, ### for subheadings\n"
                "- For straight arrows, use → ← ↑ ↓ symbols\n"
                "- For curved/hooked arrows (↳), use ↳ symbol on a NEW LINE with indentation:\n"
                "  - These indicate indented sub-points that continue from the line above\n"
                "  - Format as: [main text]\\n  ↳ [indented continuation]\n"
                "  - Each arrow should start its own line, indented with 2 spaces\n"
                "  - These are NOT tasks or checkboxes\n"
                "- For bullet points, use - (dash) for bullets, NOT asterisks\n"
                "- For checkboxes (square boxes □), use - [ ] for empty and - [x] for checked\n"
                "- IMPORTANT: Distinguish between curved arrows (↳) and checkboxes (□) - they are NOT the same\n"
                "- Use **bold** for emphasis where appropriate\n"
                "- Use `code` for any technical terms or special notation\n"
                "- Maintain line breaks and logical structure\n\n"
                "IMPORTANT - Date Detection:\n"
                "Look specifically on the RIGHT SIDE of the page at any height for dates in format dd-mm-yyyy "
                "that might be surrounded by a \"lying L\" or bracket-like shape (⌐ or similar). "
                "These dates are typically positioned at the same height as underlined titles. "
                "This is crucial for organizing the content chronologically.\n\n"
                "If you find a date on the right side:\n"
                "- Start your transcription with: \"**Date: dd-mm-yyyy**\"\n"
                "- Then add a horizontal rule: \"---\"\n"
                "- Then proceed with the content\n\n"
                "Output Format:\n"
                "1. If date found: **Date: dd-mm-yyyy**\\n---\\n[content]\n"
                "2. If no date: Just the content in Markdown format\n\n"
                "Return only the formatted Markdown text, no explanations."
            )

        try:
            # Call Claude Vision API
            message = self.client.messages.create(
                model="claude-haiku-4-5",  # Fast, cheap Haiku model good for OCR
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
                "Please transcribe all handwritten text from this image in Markdown format.\n\n"
                "Instructions:\n"
                "- Extract ALL visible handwritten text, including notes, arrows, symbols, and annotations\n"
                "- Format the output as clean Markdown with proper structure\n"
                "- Use ## for main headings, ### for subheadings\n"
                "- For straight arrows, use → ← ↑ ↓ symbols\n"
                "- For curved/hooked arrows (↳), use ↳ symbol on a NEW LINE with indentation:\n"
                "  - These indicate indented sub-points that continue from the line above\n"
                "  - Format as: [main text]\\n  ↳ [indented continuation]\n"
                "  - Each arrow should start its own line, indented with 2 spaces\n"
                "  - These are NOT tasks or checkboxes\n"
                "- For bullet points, use - (dash) for bullets, NOT asterisks\n"
                "- For checkboxes (square boxes □), use - [ ] for empty and - [x] for checked\n"
                "- IMPORTANT: Distinguish between curved arrows (↳) and checkboxes (□) - they are NOT the same\n"
                "- Use **bold** for emphasis where appropriate\n"
                "- Use `code` for any technical terms or special notation\n"
                "- Maintain line breaks and logical structure\n\n"
                "IMPORTANT - Date Detection:\n"
                "Look specifically on the RIGHT SIDE of the page at any height for dates in format dd-mm-yyyy "
                "that might be surrounded by a \"lying L\" or bracket-like shape (⌐ or similar). "
                "These dates are typically positioned at the same height as underlined titles. "
                "This is crucial for organizing the content chronologically.\n\n"
                "If you find a date on the right side:\n"
                "- Start your transcription with: \"**Date: dd-mm-yyyy**\"\n"
                "- Then add a horizontal rule: \"---\"\n"
                "- Then proceed with the content\n\n"
                "Output Format:\n"
                "1. If date found: **Date: dd-mm-yyyy**\\n---\\n[content]\n"
                "2. If no date: Just the content in Markdown format\n\n"
                "Return only the formatted Markdown text, no explanations."
            )

        try:
            # Call Claude Vision API
            message = self.client.messages.create(
                model="claude-haiku-4-5",  # Fast, cheap Haiku model good for OCR
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
