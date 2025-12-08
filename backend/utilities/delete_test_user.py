#!/usr/bin/env python3
"""Delete a test user from the database by email.

This is a helper script for cleaning up test users during development.
After deleting from the database, remember to also delete the user from
Clerk Dashboard to keep both systems in sync.

Usage:
    python delete_test_user.py <email>

Example:
    python delete_test_user.py test@example.com
"""
import sys
import sqlite3
from pathlib import Path


def delete_user(email: str, db_path: str = "rmirror.db"):
    """Delete a user from the database by email."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if user exists
    cursor.execute("SELECT id, email, clerk_user_id FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()

    if not user:
        print(f"❌ User with email '{email}' not found in database")
        conn.close()
        return False

    print(f"Found user: ID={user[0]}, Email={user[1]}, Clerk ID={user[2]}")
    print(f"Deleting user from database...")

    cursor.execute("DELETE FROM users WHERE email = ?", (email,))
    conn.commit()

    print(f"✅ User '{email}' deleted from database")
    print(f"⚠️  Don't forget to also delete this user from Clerk Dashboard!")
    print(f"   https://dashboard.clerk.com → Users → {email}")

    conn.close()
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python delete_test_user.py <email>")
        print("Example: python delete_test_user.py test@example.com")
        sys.exit(1)

    email = sys.argv[1]

    # Use the database in the backend directory
    db_path = Path(__file__).parent.parent / "rmirror.db"

    success = delete_user(email, str(db_path))
    sys.exit(0 if success else 1)
