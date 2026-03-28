#!/usr/bin/env python3
"""OCR benchmark runner — sends test PDFs through multiple models."""

import argparse
import base64
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml


def load_config(config_path: Path) -> dict:
    """Load benchmark config from YAML file."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def call_anthropic(pdf_bytes: bytes, prompt: str, model: str) -> dict:
    """Call Anthropic Claude API with PDF input. Returns dict with text, tokens, duration."""
    import anthropic

    client = anthropic.Anthropic()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    start = time.monotonic()
    message = client.messages.create(
        model=model,
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
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    duration_ms = round((time.monotonic() - start) * 1000)

    return {
        "text": message.content[0].text if message.content else "",
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
        "duration_ms": duration_ms,
    }


def call_openai(pdf_bytes: bytes, prompt: str, model: str) -> dict:
    """Call OpenAI API with PDF input. Returns dict with text, tokens, duration."""
    from openai import OpenAI

    client = OpenAI()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    start = time.monotonic()
    response = client.chat.completions.create(
        model=model,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "file",
                        "file": {
                            "filename": "page.pdf",
                            "file_data": f"data:application/pdf;base64,{pdf_b64}",
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    duration_ms = round((time.monotonic() - start) * 1000)

    return {
        "text": response.choices[0].message.content or "",
        "input_tokens": response.usage.prompt_tokens if response.usage else 0,
        "output_tokens": response.usage.completion_tokens if response.usage else 0,
        "duration_ms": duration_ms,
    }


def call_google(pdf_bytes: bytes, prompt: str, model: str) -> dict:
    """Call Google Gemini API with PDF input. Returns dict with text, tokens, duration."""
    from google import genai
    from google.genai import types

    client = genai.Client()

    start = time.monotonic()
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            prompt,
        ],
    )
    duration_ms = round((time.monotonic() - start) * 1000)

    input_tokens = 0
    output_tokens = 0
    if response.usage_metadata:
        input_tokens = response.usage_metadata.prompt_token_count or 0
        output_tokens = response.usage_metadata.candidates_token_count or 0

    return {
        "text": response.text or "",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "duration_ms": duration_ms,
    }


PROVIDERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "google": call_google,
}
