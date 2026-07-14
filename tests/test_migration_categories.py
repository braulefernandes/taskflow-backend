from alembic.config import Config
from alembic.script import ScriptDirectory


def test_category_migration_is_registered_after_auth_models() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    revision = script.get_revision("20260714_1200")

    assert revision is not None
    assert revision.down_revision == "20260713_0946"
    assert script.get_heads() == ["20260714_1200"]


def test_category_migration_contains_upgrade_and_downgrade_operations() -> None:
    migration_path = "alembic/versions/20260714_1200_add_categories.py"

    with open(migration_path, encoding="utf-8") as migration_file:
        migration = migration_file.read()

    assert '"categories"' in migration
    assert '"organization_id"' in migration
    assert '"normalized_name"' in migration
    assert "uq_categories_organization_id_normalized_name" in migration
    assert 'ondelete="RESTRICT"' in migration
    assert 'op.drop_table("categories")' in migration
