"""Migration operations that apply their schema change on selected database vendors."""

from django.db import migrations


def is_postgresql(schema_editor):
    return schema_editor.connection.vendor == "postgresql"


class PostgreSQLRunSQL(migrations.RunSQL):
    """RunSQL that runs against PostgreSQL only."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if is_postgresql(schema_editor):
            super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if is_postgresql(schema_editor):
            super().database_backwards(app_label, schema_editor, from_state, to_state)


class AlterFieldExceptPostgreSQL(migrations.AlterField):
    """AlterField whose schema change is skipped on PostgreSQL.

    The state change applies on every backend. Pair it with PostgreSQL-only SQL
    that makes the same schema change online.
    """

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if not is_postgresql(schema_editor):
            super().database_forwards(app_label, schema_editor, from_state, to_state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if not is_postgresql(schema_editor):
            super().database_backwards(app_label, schema_editor, from_state, to_state)
