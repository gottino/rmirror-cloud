#!/usr/bin/env python3
"""
Test script for todo extraction feature.

This script demonstrates:
1. Authenticate with the API
2. Trigger todo extraction for notebooks
3. List extracted todos
4. View statistics

Usage:
    python test_todo_extraction.py
"""

import httpx
import time
import json
from typing import Optional

BASE_URL = "http://localhost:8000/v1"

# Test user credentials
EMAIL = "ocr-test@example.com"
PASSWORD = "testpassword123"


class TodoExtractionTester:
    def __init__(self):
        self.token: Optional[str] = None
        self.headers = {"Content-Type": "application/json"}

    def login(self):
        """Authenticate and get access token."""
        print("🔑 Logging in...")
        response = httpx.post(
            f"{BASE_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD}
        )
        response.raise_for_status()
        data = response.json()
        self.token = data["access_token"]
        self.headers["Authorization"] = f"Bearer {self.token}"
        print(f"✅ Logged in successfully")
        return self.token

    def list_notebooks(self):
        """List user's notebooks."""
        print("\n📚 Listing notebooks...")
        response = httpx.get(f"{BASE_URL}/notebooks/", headers=self.headers)
        response.raise_for_status()
        notebooks = response.json()
        print(f"   Found {len(notebooks)} notebook(s):")
        for nb in notebooks[:10]:  # Show first 10
            print(
                f"   - {nb['visible_name']} (ID: {nb['id']}, UUID: {nb['notebook_uuid']})"
            )
        return notebooks

    def trigger_todo_extraction(self, notebook_ids: list[int] = None):
        """Trigger todo extraction for notebooks."""
        if notebook_ids:
            print(
                f"\n🚀 Triggering todo extraction for {len(notebook_ids)} specific notebook(s)..."
            )
            json_data = {"notebook_ids": notebook_ids, "force_reprocess": False}
        else:
            print(f"\n🚀 Triggering todo extraction for ALL notebooks...")
            json_data = {"force_reprocess": False}

        response = httpx.post(
            f"{BASE_URL}/todos/extract", headers=self.headers, json=json_data
        )
        response.raise_for_status()
        data = response.json()
        print(f"✅ {data['message']}")
        return data

    def list_todos(self, notebook_id: int = None, completed: bool = None, limit: int = 50):
        """List todos."""
        print("\n📋 Listing todos...")
        params = {"limit": limit}
        if notebook_id is not None:
            params["notebook_id"] = notebook_id
        if completed is not None:
            params["completed"] = completed

        response = httpx.get(
            f"{BASE_URL}/todos/", headers=self.headers, params=params
        )
        response.raise_for_status()
        todos = response.json()

        if not todos:
            print("   No todos found")
            return todos

        print(f"   Found {len(todos)} todo(s):")
        for todo in todos:
            status = "✓" if todo["completed"] else "☐"
            conf = f" (conf: {todo['confidence']:.2f})" if todo["confidence"] else ""
            print(
                f"   {status} [{todo['id']}] {todo['text'][:80]}{conf} - Page {todo['page_number']}"
            )
        return todos

    def get_todo_stats(self):
        """Get todo statistics."""
        print("\n📊 Getting todo statistics...")
        response = httpx.get(f"{BASE_URL}/todos/stats/summary", headers=self.headers)
        response.raise_for_status()
        stats = response.json()
        print(f"   Total todos: {stats['total_todos']}")
        print(f"   Completed: {stats['completed_todos']}")
        print(f"   Pending: {stats['pending_todos']}")
        print(f"   Notebooks with todos: {stats['notebooks_with_todos']}")
        return stats

    def update_todo(self, todo_id: int, completed: bool):
        """Update a todo's completion status."""
        print(f"\n✏️ Updating todo {todo_id}...")
        response = httpx.patch(
            f"{BASE_URL}/todos/{todo_id}",
            headers=self.headers,
            json={"completed": completed},
        )
        response.raise_for_status()
        data = response.json()
        status = "✓" if data["completed"] else "☐"
        print(f"   {status} Todo updated: {data['text'][:60]}...")
        return data


def main():
    """Run the end-to-end test."""
    print("=" * 60)
    print("🧪 Todo Extraction Test")
    print("=" * 60)

    tester = TodoExtractionTester()

    try:
        # Step 1: Login
        tester.login()

        # Step 2: List notebooks
        notebooks = tester.list_notebooks()

        if not notebooks:
            print("\n❌ No notebooks found. Please upload some notebooks first.")
            return

        # Step 3: Check if there are already todos
        print("\n📊 Checking existing todos...")
        existing_todos = tester.list_todos(limit=5)

        # Step 4: Trigger todo extraction for first notebook or all
        if len(notebooks) > 0:
            # Extract from first notebook only
            first_nb = notebooks[0]
            tester.trigger_todo_extraction(notebook_ids=[first_nb["id"]])
        else:
            # Extract from all notebooks
            tester.trigger_todo_extraction()

        # Step 5: Wait a bit for background task
        print("\n⏳ Waiting 3 seconds for extraction to process...")
        time.sleep(3)

        # Step 6: List todos again
        todos = tester.list_todos(limit=20)

        # Step 7: Get statistics
        tester.get_todo_stats()

        # Step 8: If we have todos, test updating one
        if todos and len(todos) > 0:
            first_todo = todos[0]
            print(f"\n🧪 Testing todo update...")
            tester.update_todo(first_todo["id"], completed=not first_todo["completed"])

            # Check the update
            tester.list_todos(limit=5)

        print("\n" + "=" * 60)
        print("✅ Test completed successfully!")
        print("=" * 60)

    except httpx.HTTPStatusError as e:
        print(f"\n❌ HTTP Error: {e}")
        print(f"   Response: {e.response.text}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
