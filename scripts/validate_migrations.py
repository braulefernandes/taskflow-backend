import os
import subprocess
import sys
from pathlib import Path

TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"
SAFE_TEST_MARKERS = ("test", "_test", "-test")


def is_safe_test_database_url(database_url: str) -> bool:
    normalized_url = database_url.lower()
    return (
        normalized_url.startswith("postgresql+psycopg://")
        and any(marker in normalized_url for marker in SAFE_TEST_MARKERS)
        and "prod" not in normalized_url
        and "production" not in normalized_url
    )


def run_alembic(args: list[str], env: dict[str, str]) -> None:
    command = [sys.executable, "-m", "alembic", *args]
    subprocess.run(command, cwd=Path(__file__).resolve().parents[1], env=env, check=True)


def main() -> int:
    test_database_url = os.environ.get(TEST_DATABASE_URL_ENV)
    if not test_database_url:
        print(
            f"Defina {TEST_DATABASE_URL_ENV} com uma URL PostgreSQL de teste explicita.",
            file=sys.stderr,
        )
        return 2

    if not is_safe_test_database_url(test_database_url):
        print(
            f"{TEST_DATABASE_URL_ENV} precisa apontar para PostgreSQL de teste e nao pode parecer producao.",
            file=sys.stderr,
        )
        return 2

    env = os.environ.copy()
    env["DATABASE_URL"] = test_database_url

    run_alembic(["upgrade", "head"], env)
    run_alembic(["downgrade", "base"], env)
    run_alembic(["upgrade", "head"], env)
    print("Migrations validadas com sucesso em banco PostgreSQL de teste.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
