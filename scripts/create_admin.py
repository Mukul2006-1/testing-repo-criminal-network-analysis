"""Create the first local admin user (documented bootstrap).

The password is read interactively (never from CLI args or logs) unless
ADMIN_PASSWORD is set in the local shell for container seeding. The email
may come from argv[1] or ADMIN_EMAIL. Nothing here hardcodes credentials.

Usage:
    python scripts/create_admin.py [email] [--name "Full Name"]
    ADMIN_EMAIL=a@b.c ADMIN_PASSWORD=... python scripts/create_admin.py

The store defaults to data/processed/documents.db (DOCUMENT_DB_PATH
overrides, mirroring the backend).
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import uuid
from datetime import datetime, timezone

BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database.documents import DocumentStore, default_db_path  # noqa: E402
from app.services import auth as auth_svc  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Create first admin user.")
    parser.add_argument("email", nargs="?",
                        default=os.environ.get("ADMIN_EMAIL", ""))
    parser.add_argument("--name", default=os.environ.get("ADMIN_NAME",
                                                         "Administrator"))
    args = parser.parse_args(argv)

    email = (args.email or "").strip().lower()
    if not email:
        email = input("Admin email: ").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass(
        "Admin password (min 8 chars): ")
    try:
        auth_svc.validate_password_policy(password)
    except Exception as exc:
        print(f"Rejected: {exc}")
        return 2

    store = DocumentStore(os.environ.get("DOCUMENT_DB_PATH",
                                         default_db_path()))
    if store.get_user_by_email(email) is not None:
        print(f"User already exists: {email}")
        return 1
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    store.create_user({"id": f"user_{uuid.uuid4().hex[:8]}", "name": args.name,
                       "email": email,
                       "password_hash": auth_svc.hash_password(password),
                       "role": "ADMIN", "created_at": now, "updated_at": now})
    print(f"Admin created: {email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
