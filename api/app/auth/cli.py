"""Account management. There is deliberately no public signup.

    python -m app.auth.cli create-user david
    python -m app.auth.cli set-password david
    python -m app.auth.cli logout-everywhere david
    python -m app.auth.cli disable david
    python -m app.auth.cli list

Passwords are read with a hidden prompt, never from arguments or the environment.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from .. import db
from . import service


def _password() -> str:
    first = getpass.getpass("New password: ")
    if first != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords did not match.")
    return first


def _user_id(conn, username: str) -> int:
    row = conn.execute("SELECT id FROM auth.users WHERE username=%s", (service.normalize(username),)).fetchone()
    if not row:
        raise SystemExit(f"No such user: {username}")
    return row[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("create-user", "set-password", "logout-everywhere", "disable", "enable"):
        sub.add_parser(name).add_argument("username")
    sub.add_parser("list")
    args = parser.parse_args(argv)

    with db.connect() as conn:
        if args.cmd == "list":
            for username, disabled, last in conn.execute(
                    "SELECT username, disabled, last_login_at FROM auth.users ORDER BY id"):
                print(f"{username}\t{'disabled' if disabled else 'active'}\tlast login: {last or 'never'}")
            return 0
        if args.cmd == "create-user":
            try:
                service.create_user(conn, args.username, _password())
            except ValueError as problem:
                raise SystemExit(str(problem))
            print(f"Created {service.normalize(args.username)}.")
        elif args.cmd == "set-password":
            uid = _user_id(conn, args.username)
            try:
                service.set_password(conn, uid, _password())
            except ValueError as problem:
                raise SystemExit(str(problem))
            print(f"Password changed; {service.revoke_all(conn, uid)} session(s) ended.")
        elif args.cmd == "logout-everywhere":
            print(f"{service.revoke_all(conn, _user_id(conn, args.username))} session(s) ended.")
        elif args.cmd in ("disable", "enable"):
            uid = _user_id(conn, args.username)
            conn.execute("UPDATE auth.users SET disabled=%s WHERE id=%s", (args.cmd == "disable", uid))
            if args.cmd == "disable":
                service.revoke_all(conn, uid)
            conn.commit()
            print(f"{args.cmd}d {args.username}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
