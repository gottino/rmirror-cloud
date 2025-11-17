#!/usr/bin/env python3
"""Reset user password."""
import sys
import bcrypt
from sqlalchemy import create_engine, text

def reset_password(email: str, new_password: str):
    """Reset password for a user."""
    engine = create_engine("sqlite:///rmirror.db")
    
    # Hash the new password with bcrypt
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), salt).decode('utf-8')
    
    # Update the user
    with engine.connect() as conn:
        result = conn.execute(
            text("UPDATE users SET hashed_password = :hash WHERE email = :email"),
            {"hash": hashed_password, "email": email}
        )
        conn.commit()
        
        if result.rowcount > 0:
            print(f"✅ Password updated for {email}")
        else:
            print(f"❌ User {email} not found")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python reset_password.py EMAIL PASSWORD")
        sys.exit(1)
    
    reset_password(sys.argv[1], sys.argv[2])
