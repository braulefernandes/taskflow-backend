from scripts.validate_migrations import is_safe_test_database_url


def test_migration_validation_accepts_explicit_postgresql_test_database() -> None:
    assert is_safe_test_database_url(
        "postgresql+psycopg://taskflow_test:secret@localhost:5432/taskflow_test"
    )


def test_migration_validation_rejects_production_like_database() -> None:
    assert not is_safe_test_database_url(
        "postgresql+psycopg://taskflow:secret@localhost:5432/taskflow_prod"
    )
    assert not is_safe_test_database_url(
        "postgresql+psycopg://taskflow:secret@localhost:5432/taskflow"
    )


def test_migration_validation_rejects_non_postgresql_url() -> None:
    assert not is_safe_test_database_url("sqlite:///:memory:")
