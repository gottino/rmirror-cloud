#!/usr/bin/env python3
"""
Test script for Notion sync integration.

This script demonstrates the end-to-end workflow:
1. Authenticate with the API
2. Create a Notion integration configuration
3. Test the Notion connection
4. Trigger a sync for the test notebook
5. Monitor sync status

Requirements:
- API running on localhost:8000
- Valid Notion API token
- Notion database ID with required properties (Name, UUID, Path, Pages)

Usage:
    python test_notion_sync.py [NOTION_TOKEN] [DATABASE_ID]

Or set environment variables:
    NOTION_TOKEN=secret_xxx DATABASE_ID=xxx python test_notion_sync.py
"""

import httpx
import time
import json
import os
import sys
from typing import Optional

BASE_URL = "http://localhost:8000/v1"

# Test user credentials (user with actual notebook data)
EMAIL = "ocr-test@example.com"
PASSWORD = "testpassword123"

# Notebook to sync
TEST_NOTEBOOK_UUID = "a1b2c3d4-5678-90ab-cdef-1234567890ab"


class NotionSyncTester:
    def __init__(self):
        self.token: Optional[str] = None
        self.headers = {"Content-Type": "application/json"}

    def login(self):
        """Authenticate and get access token."""
        print("🔑 Logging in...")
        response = httpx.post(
            f"{BASE_URL}/auth/login",
            json={"email": EMAIL, "password": PASSWORD}
        )
        response.raise_for_status()
        data = response.json()
        self.token = data["access_token"]
        self.headers["Authorization"] = f"Bearer {self.token}"
        print(f"✅ Logged in successfully")
        return self.token

    def create_notion_integration(self, api_token: str, database_id: str):
        """Create Notion integration configuration."""
        print("\n📝 Creating Notion integration...")
        response = httpx.post(
            f"{BASE_URL}/integrations/",
            headers=self.headers,
            json={
                "target_name": "notion",
                "is_enabled": True,
                "config": {
                    "api_token": api_token,
                    "database_id": database_id
                }
            }
        )

        if response.status_code == 400 and "already exists" in response.text:
            print("⚠️  Integration already exists, updating...")
            response = httpx.put(
                f"{BASE_URL}/integrations/notion",
                headers=self.headers,
                json={
                    "target_name": "notion",
                    "is_enabled": True,
                    "config": {
                        "api_token": api_token,
                        "database_id": database_id
                    }
                }
            )

        response.raise_for_status()
        data = response.json()
        print(f"✅ Integration created/updated: {data['target_name']}")
        return data

    def test_notion_connection(self):
        """Test the Notion connection."""
        print("\n🔌 Testing Notion connection...")
        response = httpx.post(
            f"{BASE_URL}/integrations/notion/test",
            headers=self.headers
        )
        response.raise_for_status()
        data = response.json()

        if data["success"]:
            print(f"✅ Connection successful!")
            if data.get("details"):
                print(f"   Database: {data['details'].get('database_title', 'Unknown')}")
                print(f"   Capabilities: {data['details'].get('capabilities', {})}")
        else:
            print(f"❌ Connection failed: {data.get('message')}")

        return data

    def get_notebook_details(self):
        """Get details about the test notebook."""
        print(f"\n📓 Getting test notebook details...")
        response = httpx.get(
            f"{BASE_URL}/notebooks/uuid/{TEST_NOTEBOOK_UUID}",
            headers=self.headers
        )
        response.raise_for_status()
        data = response.json()
        print(f"   Title: {data.get('visible_name', data.get('title', 'Unknown'))}")
        print(f"   Path: {data.get('full_path', 'N/A')}")
        print(f"   UUID: {data['notebook_uuid']}")
        return data

    def trigger_sync(self, notebook_uuid: str = None, limit: int = 5):
        """Trigger sync to Notion."""
        if notebook_uuid:
            print(f"\n🚀 Triggering sync for specific notebook: {notebook_uuid}...")
            json_data = {
                "target_name": "notion",
                "item_type": None,  # All types
                "notebook_uuids": [notebook_uuid]
            }
        else:
            print(f"\n🚀 Triggering sync for Notion (limit: {limit} notebooks)...")
            json_data = {
                "target_name": "notion",
                "item_type": None,  # All types
                "limit": limit
            }

        response = httpx.post(
            f"{BASE_URL}/sync/trigger",
            headers=self.headers,
            json=json_data
        )
        response.raise_for_status()
        data = response.json()
        print(f"✅ Sync started: {data['message']}")
        return data

    def get_sync_stats(self):
        """Get sync statistics."""
        print("\n📊 Getting sync statistics...")
        response = httpx.get(
            f"{BASE_URL}/sync/stats?target_name=notion",
            headers=self.headers
        )
        response.raise_for_status()
        data = response.json()
        print(f"   Total records: {data['total_records']}")
        print(f"   Status counts: {data['status_counts']}")
        print(f"   Type counts: {data['type_counts']}")
        return data

    def get_sync_status(self):
        """Get detailed sync status for Notion."""
        print("\n📈 Getting sync status...")
        response = httpx.get(
            f"{BASE_URL}/sync/status/notion",
            headers=self.headers
        )
        response.raise_for_status()
        data = response.json()
        print(f"   Target: {data['target_name']}")
        print(f"   Enabled: {data['is_enabled']}")
        print(f"   Last synced: {data['last_synced_at']}")
        if data.get('stats'):
            print(f"   Stats: {json.dumps(data['stats'], indent=2)}")
        return data

    def list_integrations(self):
        """List all integrations."""
        print("\n📋 Listing all integrations...")
        response = httpx.get(
            f"{BASE_URL}/integrations/",
            headers=self.headers
        )
        response.raise_for_status()
        data = response.json()
        for integration in data:
            print(f"   - {integration['target_name']}: "
                  f"{'enabled' if integration['is_enabled'] else 'disabled'}")
        return data


def main():
    """Run the end-to-end test."""
    print("=" * 60)
    print("🧪 Notion Sync Integration Test")
    print("=" * 60)

    # Get Notion credentials from command line args, environment variables, or user input
    notion_token = None
    database_id = None

    # Try command line arguments
    if len(sys.argv) >= 2:
        notion_token = sys.argv[1]
    if len(sys.argv) >= 3:
        database_id = sys.argv[2]

    # Try environment variables
    if not notion_token:
        notion_token = os.environ.get("NOTION_TOKEN")
    if not database_id:
        database_id = os.environ.get("DATABASE_ID")

    # Default database ID from provided Notion link
    default_db_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    if not database_id:
        database_id = default_db_id

    # Interactive fallback if running in terminal
    if not notion_token and sys.stdin.isatty():
        print("\nTo test the Notion integration, you need:")
        print("1. A Notion integration API token")
        print("2. A Notion database ID")
        print("\nThe database should have these properties:")
        print("   - Name (title)")
        print("   - UUID (rich text)")
        print("   - Path (rich text)")
        print("   - Pages (number)")
        print()

        notion_token = input("Enter your Notion API token: ").strip()
        if not notion_token:
            print("❌ No API token provided, exiting.")
            return

        database_id_input = input(f"Enter your Notion database ID (or press Enter for default): ").strip()
        database_id = database_id_input if database_id_input else default_db_id

    if not notion_token:
        print("❌ No Notion API token provided. Set NOTION_TOKEN env var or pass as argument.")
        return

    print(f"\n✓ Using database ID: {database_id}")

    # Run the test
    tester = NotionSyncTester()

    try:
        # Step 1: Login
        tester.login()

        # Step 2: Create/update integration
        tester.create_notion_integration(notion_token, database_id)

        # Step 3: Test connection
        conn_result = tester.test_notion_connection()
        if not conn_result["success"]:
            print("\n❌ Connection test failed, cannot proceed.")
            return

        # Step 4: List integrations
        tester.list_integrations()

        # Step 5: Get notebook details
        tester.get_notebook_details()

        # Step 6: Trigger sync for test notebook specifically
        tester.trigger_sync(notebook_uuid=TEST_NOTEBOOK_UUID)

        # Step 7: Wait a bit for background task
        print("\n⏳ Waiting 5 seconds for sync to process...")
        time.sleep(5)

        # Step 8: Check sync stats
        tester.get_sync_stats()

        # Step 9: Get detailed status
        tester.get_sync_status()

        print("\n" + "=" * 60)
        print("✅ Test completed successfully!")
        print("=" * 60)
        print("\n💡 Check your Notion database to see the synced notebook!")

    except httpx.HTTPStatusError as e:
        print(f"\n❌ HTTP Error: {e}")
        print(f"   Response: {e.response.text}")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    main()
