#!/usr/bin/env python3
"""Upload Marton .content file to production to update mapping."""

import asyncio
import httpx
from pathlib import Path

NOTEBOOK_UUID = "a5cb6010-b0f6-4bc6-ac80-9ef341708db7"
CONTENT_FILE = Path(
    f"/Users/gabriele/Library/Containers/com.remarkable.desktop/Data/Library/Application Support/remarkable/desktop/{NOTEBOOK_UUID}.content"
)
API_URL = "https://api.rmirror.cloud/v1"
# You'll need to provide a valid auth token
AUTH_TOKEN = "your-clerk-session-token"  # Get from browser dev tools

async def upload():
    async with httpx.AsyncClient(timeout=30.0) as client:
        with open(CONTENT_FILE, 'rb') as f:
            response = await client.post(
                f"{API_URL}/notebooks/{NOTEBOOK_UUID}/content",
                files={"content_file": (CONTENT_FILE.name, f, "application/json")},
                headers={"Authorization": f"Bearer {AUTH_TOKEN}"}
            )

        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")

if __name__ == "__main__":
    asyncio.run(upload())
