"""Create the first system administrator, or reset a lost admin password.

    python -m app.auth.create_admin --email admin@example.org --name "Ada Obi"

The password is read from the terminal (never from arguments, which end up in shell
history) or, for automation, from the VERIVOTE_ADMIN_PASSWORD environment variable."""

import argparse
import getpass
import os
import sys

from sqlalchemy import func, select

from app.auth import passwords, service
from app.db.enums import Role
from app.db.models import User
from app.evidence.db import evidence_session_factory


def _read_password(email: str) -> str:
    supplied = os.environ.get("VERIVOTE_ADMIN_PASSWORD")
    if supplied:
        if problem := passwords.password_problem(supplied, email):
            sys.exit(f"VERIVOTE_ADMIN_PASSWORD is not acceptable: {problem}")
        return supplied
    while True:
        first = getpass.getpass("Password: ")
        if problem := passwords.password_problem(first, email):
            print(problem)
            continue
        if getpass.getpass("Repeat password: ") != first:
            print("The passwords do not match.")
            continue
        return first


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default=None)
    args = parser.parse_args(argv)
    email = service.normalise_email(args.email)

    with evidence_session_factory()() as db:
        existing = db.scalar(select(User).where(func.lower(User.email) == email))
        password = _read_password(email)
        if existing is None:
            service.create_account(
                db,
                email=email,
                display_name=args.name,
                roles=[Role.SYSTEM_ADMIN],
                password=password,
                actor=None,
            )
            print(f"Created system admin {email}.")
            return

        roles = service.roles_of(db, existing.id)
        credential = db.get(service.UserCredential, existing.id)
        if credential is None:
            db.add(
                service.UserCredential(
                    user_id=existing.id, password_hash=passwords.hash_password(password)
                )
            )
        else:
            credential.password_hash = passwords.hash_password(password)
            credential.token_version += 1
            credential.must_change_password = False
            credential.failed_attempts = 0
            credential.locked_until = None
        if Role.SYSTEM_ADMIN not in roles:
            db.add(service.RoleAssignment(user_id=existing.id, role=Role.SYSTEM_ADMIN))
        existing.is_active = True
        db.flush()
        service.append_event(
            db,
            entity_type=service.ENTITY_ACCOUNT,
            entity_id=existing.id,
            action="account.admin_restored",
            actor_id=None,
        )
        db.commit()
        print(f"Updated {email}: password set and system admin role ensured.")


if __name__ == "__main__":
    main()
