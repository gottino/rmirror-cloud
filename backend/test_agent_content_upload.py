#!/usr/bin/env python3
"""
Test script to verify the agent can upload .content files to the backend.

This simulates what the updated agent will do:
1. Upload pages (.rm files)
2. Upload .content file to map pages to the notebook
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv(Path(__file__).parent / '.env')

# Configuration
BACKEND_URL = "http://localhost:8000/v1"
# Use development bypass token (works when DEBUG=true in .env)
API_KEY = os.getenv('CLERK_API_KEY', 'dev-mode-bypass')

# Test notebook UUID (one that exists in the local database with pages)
NOTEBOOK_UUID = "445c3ac6-6a65-44d6-9995-34df30079037"  # Abilio - has 32 pages
CONTENT_FILE = Path(
    f"/Users/gabriele/Library/Containers/com.remarkable.desktop/Data/Library/Application Support/remarkable/desktop/{NOTEBOOK_UUID}.content"
)


async def upload_content_file(notebook_uuid: str, content_path: Path):
    """Upload a .content file to the backend."""

    if not content_path.exists():
        print(f"❌ Content file not found: {content_path}")
        return False

    # Read the content file to see what it contains
    with open(content_path, 'r') as f:
        content_data = json.load(f)

    pages_array = content_data.get('pages', [])
    if not pages_array and 'cPages' in content_data:
        c_pages = content_data['cPages'].get('pages', [])
        pages_array = [p['id'] for p in c_pages if isinstance(p, dict) and 'id' in p]

    print(f"📄 Content file has {len(pages_array)} pages")
    print()

    # Upload the .content file
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"📤 Uploading .content file to: {BACKEND_URL}/notebooks/{notebook_uuid}/content")

        with open(content_path, 'rb') as f:
            response = await client.post(
                f"{BACKEND_URL}/notebooks/{notebook_uuid}/content",
                files={"content_file": (content_path.name, f, "application/json")},
                headers={"Authorization": f"Bearer {API_KEY}"}
            )

        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success!")
            print(f"   Pages in .content: {result.get('pages_in_content')}")
            print(f"   Pages mapped: {result.get('pages_mapped')}")
            return True
        else:
            print(f"❌ Failed: {response.text}")
            return False


async def main():
    """Main test function."""
    print("=" * 70)
    print("  🧪 Test Agent Content Upload")
    print("=" * 70)
    print()
    print(f"Using API key: {API_KEY}")
    print()

    # Test uploading the .content file
    success = await upload_content_file(NOTEBOOK_UUID, CONTENT_FILE)

    print()
    print("=" * 70)
    if success:
        print("  ✅ Test passed - agent content upload works!")
    else:
        print("  ❌ Test failed")
    print("=" * 70)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
