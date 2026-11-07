"""Server commands for operators (not part of the API).

    python -m app.cli create-admin --name "Owner Name" --phone 9876543210

Creates the first ADMIN account on a fresh production database (no demo seeds there). The
password is read from ADMIN_PASSWORD or asked for interactively; it is stored hashed and
never printed. Further staff and retailers are created from the Admin portal.
"""

import argparse
import getpass
import os
import re
import sys

from sqlalchemy import select

from app.core.constants import UserRole
from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models import User


def create_admin(name: str, phone: str, password: str, email: str | None) -> str:
    if not re.fullmatch(r"[6-9]\d{9}", phone):
        raise ValueError("phone must be a 10-digit Indian mobile number")
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.phone == phone)) is not None:
            raise ValueError(f"an account with mobile {phone} already exists")
        db.add(User(name=name.strip(), phone=phone, email=(email or "").strip().lower() or None,
                    role=UserRole.ADMIN, password_hash=hash_password(password)))
        db.commit()
    return f"Admin {name.strip()} ({phone}) created. Log in on the Staff tab."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-admin", help="create an ADMIN account")
    admin.add_argument("--name", required=True)
    admin.add_argument("--phone", required=True, help="10-digit mobile number (the login)")
    admin.add_argument("--email")
    args = parser.parse_args(argv)

    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password for the admin (8+ characters): ")
    try:
        print(create_admin(args.name, args.phone, password, args.email))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
