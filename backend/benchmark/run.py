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


def discover_pages(pages_dir: Path) -> list[Path]:
    """Find all PDF files in the pages directory."""
    pages = sorted(pages_dir.glob("*.pdf"))
    if not pages:
        print(f"ERROR: No PDF files found in {pages_dir}/")
        print("Add test PDFs to benchmark/pages/ and try again.")
        sys.exit(1)
    return pages


def run_benchmark(config: dict, model_filter: list[str] | None, runs_override: int | None, dry_run: bool):
    """Execute the benchmark: send each PDF through each model N times."""
    benchmark_dir = Path(__file__).parent
    pages_dir = benchmark_dir / "pages"
    results_dir = benchmark_dir / "results"

    pages = discover_pages(pages_dir)
    runs_per_page = runs_override or config.get("runs_per_page", 3)
    prompt = config["prompt"]
    models = config["models"]

    # Filter models if requested
    if model_filter:
        models = {k: v for k, v in models.items() if k in model_filter}
        if not models:
            print(f"ERROR: No matching models. Available: {list(config['models'].keys())}")
            sys.exit(1)

    # Check which models have API keys available
    available_models = {}
    for name, cfg in models.items():
        env_key = cfg["env_key"]
        if os.environ.get(env_key):
            available_models[name] = cfg
        else:
            print(f"WARNING: Skipping {name} — {env_key} not set")

    if not available_models:
        print("ERROR: No models available. Set at least one API key.")
        sys.exit(1)

    total_calls = len(available_models) * len(pages) * runs_per_page
    print(f"\nBenchmark: {len(available_models)} models x {len(pages)} pages x {runs_per_page} runs = {total_calls} API calls")

    if dry_run:
        print("\n[DRY RUN] Would execute:")
        for name in available_models:
            print(f"  {name}: {len(pages)} pages x {runs_per_page} runs = {len(pages) * runs_per_page} calls")
        return

    # Create timestamped results directory
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    run_dir = results_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # Track metadata
    meta = {
        "timestamp": timestamp,
        "prompt": prompt,
        "runs_per_page": runs_per_page,
        "pages": [p.name for p in pages],
        "models": {},
    }

    call_num = 0
    for model_name, model_cfg in available_models.items():
        provider_fn = PROVIDERS[model_cfg["provider"]]
        model_id = model_cfg["model"]
        model_dir = run_dir / model_name
        model_dir.mkdir(exist_ok=True)

        model_meta = {"calls": 0, "total_duration_ms": 0, "total_input_tokens": 0, "total_output_tokens": 0}

        for page_path in pages:
            page_stem = page_path.stem
            pdf_bytes = page_path.read_bytes()

            for run_num in range(1, runs_per_page + 1):
                call_num += 1
                print(f"  [{call_num}/{total_calls}] {model_name} / {page_stem} / run {run_num}...", end=" ", flush=True)

                output_path = model_dir / f"{page_stem}_run{run_num}.md"

                try:
                    result = provider_fn(pdf_bytes, prompt, model_id)
                    output_path.write_text(result["text"], encoding="utf-8")
                    model_meta["calls"] += 1
                    model_meta["total_duration_ms"] += result["duration_ms"]
                    model_meta["total_input_tokens"] += result["input_tokens"]
                    model_meta["total_output_tokens"] += result["output_tokens"]
                    print(f"{result['duration_ms']}ms, {result['output_tokens']} tokens")
                except Exception as e:
                    error_msg = f"ERROR: {type(e).__name__}: {e}"
                    output_path.write_text(error_msg, encoding="utf-8")
                    model_meta["calls"] += 1
                    print(f"FAILED: {e}")

        if model_meta["calls"] > 0:
            model_meta["avg_duration_ms"] = round(model_meta["total_duration_ms"] / model_meta["calls"])
        meta["models"][model_name] = model_meta

    # Write metadata
    meta_path = run_dir / "meta.yaml"
    with open(meta_path, "w") as f:
        yaml.dump(meta, f, default_flow_style=False, sort_keys=False)

    print(f"\nResults saved to: {run_dir}")
    print(f"Run 'python benchmark/score.py --run {timestamp}' to score.")


def main():
    parser = argparse.ArgumentParser(description="OCR Benchmark Runner")
    parser.add_argument("--models", type=str, help="Comma-separated model keys to run (default: all)")
    parser.add_argument("--runs", type=int, help="Override runs_per_page from config")
    parser.add_argument("--dry-run", action="store_true", help="Show what would execute without calling APIs")
    parser.add_argument("--config", type=str, default=None, help="Path to config.yaml")
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else Path(__file__).parent / "config.yaml"
    config = load_config(config_path)

    model_filter = [m.strip() for m in args.models.split(",")] if args.models else None

    run_benchmark(config, model_filter, args.runs, args.dry_run)


if __name__ == "__main__":
    main()
