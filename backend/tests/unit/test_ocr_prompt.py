"""The OCR prompt names no language unless OCR_LANGUAGE_HINT is set."""

from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings


def test_language_hint_defaults_to_empty():
    assert Settings(secret_key="x").ocr_language_hint == ""


def test_default_prompt_names_no_language():
    from app.core.ocr_service import build_ocr_prompt

    prompt = build_ocr_prompt("")
    assert "German" not in prompt
    assert "English" not in prompt
    assert "Transcribe all handwritten text from this page." in prompt


def test_prompt_includes_configured_hint():
    from app.core.ocr_service import build_ocr_prompt

    prompt = build_ocr_prompt("French and Italian")
    assert "French and Italian" in prompt
    assert "German" not in prompt


def test_blank_hint_is_treated_as_unset():
    from app.core.ocr_service import build_ocr_prompt

    assert build_ocr_prompt("   ") == build_ocr_prompt("")


@pytest.mark.asyncio
async def test_service_sends_prompt_built_from_setting():
    from app.core.ocr_service import OCRService, build_ocr_prompt

    response = MagicMock(text="text", usage_metadata=None)
    with patch("app.core.ocr_service.genai.Client") as client_cls, patch(
        "app.core.ocr_service.settings.ocr_language_hint", "Dutch"
    ):
        generate = client_cls.return_value.models.generate_content
        generate.return_value = response
        await OCRService(api_key="test-key").extract_text_from_pdf(b"%PDF-1.4")

    sent_prompt = generate.call_args.kwargs["contents"][1]
    assert sent_prompt == build_ocr_prompt("Dutch")
    assert "Dutch" in sent_prompt
