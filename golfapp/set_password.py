"""Passwort eines Spielers setzen, z.B. wenn es vergessen wurde.

    python -m golfapp.set_password "Name"

Das Passwort wird verdeckt abgefragt. DATABASE_PATH bestimmt die Datenbank.
"""

import getpass
import sqlite3
import sys

from . import create_app
from .auth import hash_password, password_problem


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__.strip())
        return 2
    app = create_app()
    conn = sqlite3.connect(app.config["DATABASE"])
    row = conn.execute("SELECT id, name FROM players WHERE name = ? COLLATE NOCASE", (argv[0],)).fetchone()
    if row is None:
        print(f"Spieler „{argv[0]}“ nicht gefunden.")
        return 1
    password = getpass.getpass(f"Neues Passwort für {row[1]}: ")
    problem = password_problem(password, getpass.getpass("Wiederholen: "))
    if problem:
        print(problem)
        return 1
    conn.execute("UPDATE players SET password_hash = ? WHERE id = ?", (hash_password(password), row[0]))
    conn.commit()
    print(f"Passwort für {row[1]} gesetzt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
