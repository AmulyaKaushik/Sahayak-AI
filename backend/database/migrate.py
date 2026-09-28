import pathlib

import psycopg

from settings import settings

MIGRATIONS_DIR = pathlib.Path(__file__).parent / "migrations"


def run_migrations() -> list[str]:
    applied = []
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        already_applied = {
            row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
        }

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in already_applied:
                continue
            conn.execute(path.read_text())
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
            applied.append(path.name)

    return applied


if __name__ == "__main__":
    for name in run_migrations():
        print(f"applied {name}")
