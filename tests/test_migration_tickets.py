from alembic.config import Config
from alembic.script import ScriptDirectory


def test_ticket_migration_is_registered_after_categories() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision("20260714_1600")

    assert revision is not None
    assert revision.down_revision == "20260714_1200"
    assert script.get_heads() == ["20260714_1600"]


def test_ticket_migration_has_complete_upgrade_and_downgrade() -> None:
    with open(
        "alembic/versions/20260714_1600_add_tickets.py", encoding="utf-8"
    ) as file:
        migration = file.read()

    assert '"tickets"' in migration
    assert 'name="ticket_status"' in migration
    assert 'name="ticket_priority"' in migration
    assert 'server_default="PENDING"' in migration
    assert 'server_default="MEDIUM"' in migration
    assert "OVERDUE" not in migration
    assert migration.count('ondelete="RESTRICT"') == 4
    assert 'op.drop_table("tickets")' in migration
    assert "ticket_priority_enum.drop" in migration
    assert "ticket_status_enum.drop" in migration
