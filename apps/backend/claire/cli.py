import argparse
from getpass import getpass

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .config import Settings
from .db import Family, User
from .identity import passwords


def main():
    parser = argparse.ArgumentParser(description="Offline CLAIRE account provisioning")
    parser.add_argument("email")
    parser.add_argument("--family-id")
    parser.add_argument("--family-name", default="My family")
    parser.add_argument("--role", choices=["family_admin", "member", "reader"], default="member")
    args = parser.parse_args()
    password = getpass("Password (at least 14 characters): ")
    if len(password) < 14 or password != getpass("Confirm password: "):
        parser.error("Passwords must match and contain at least 14 characters")
    engine = create_engine(Settings().db_url())
    with Session(engine) as db:
        if db.scalar(select(User).where(User.email == args.email.lower())):
            parser.error("Account already exists")
        if args.family_id:
            family = db.get(Family, args.family_id)
            if not family:
                parser.error("Family not found")
        else:
            family = Family(name=args.family_name)
            db.add(family)
            db.flush()
        db.add(
            User(
                email=args.email.lower(),
                family_id=family.id,
                password_hash=passwords.hash(password),
                role=args.role,
            )
        )
        db.commit()
        print(f"Account created. Family ID: {family.id}")


if __name__ == "__main__":
    main()
