from alembic.config import Config
from alembic.script import ScriptDirectory


MIGRATION_PATH = "alembic/versions/20260715_1500_add_ticket_comments_and_history.py"


def test_activity_migration_is_registered_after_sprint_three() -> None:
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revision = script.get_revision("20260715_1500")

    assert revision is not None
    assert revision.down_revision == "20260714_1600"
    assert script.get_heads() == ["20260715_1500"]


def test_activity_migration_has_complete_upgrade_and_downgrade() -> None:
    with open(MIGRATION_PATH, encoding="utf-8") as file:
        migration = file.read()

    assert '"ticket_comments"' in migration
    assert '"ticket_history"' in migration
    assert 'name="ticket_history_action"' in migration
    assert migration.count('ondelete="RESTRICT"') == 4
    assert "ix_ticket_comments_ticket_id_created_at" in migration
    assert "ix_ticket_history_ticket_id_created_at" in migration
    assert 'op.drop_table("ticket_history")' in migration
    assert 'op.drop_table("ticket_comments")' in migration
    assert "ticket_history_action_enum.drop" in migration
    for action in (
        "CREATED",
        "TITLE_CHANGED",
        "DESCRIPTION_CHANGED",
        "CATEGORY_CHANGED",
        "PRIORITY_CHANGED",
        "DUE_DATE_CHANGED",
        "ASSIGNED",
        "ASSIGNEE_CHANGED",
        "ASSIGNEE_REMOVED",
        "STATUS_CHANGED",
        "COMPLETED",
        "REOPENED",
        "CANCELLED",
    ):
        assert f'"{action}"' in migration
