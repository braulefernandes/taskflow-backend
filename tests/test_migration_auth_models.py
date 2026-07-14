from alembic.config import Config
from alembic.script import ScriptDirectory


def test_initial_auth_migration_is_registered() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    revision = script.get_revision("20260713_0946")
    assert revision is not None
    assert revision.down_revision is None


def test_initial_auth_migration_contains_expected_operations() -> None:
    migration_path = "alembic/versions/20260713_0946_initial_auth_models.py"

    with open(migration_path, encoding="utf-8") as migration_file:
        migration = migration_file.read()

    assert 'name="organization_role"' in migration
    assert '"ADMIN"' in migration
    assert '"MANAGER"' in migration
    assert '"AGENT"' in migration
    assert '"REQUESTER"' in migration
    assert '"users"' in migration
    assert '"organizations"' in migration
    assert '"organization_members"' in migration
    assert '"password_reset_tokens"' in migration
    assert 'ondelete="RESTRICT"' in migration
    assert "organization_role_enum.drop" in migration
