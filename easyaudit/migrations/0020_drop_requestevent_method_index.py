# NOTE (pipefile fork): drops method's index and its *_like twin; nothing hot filters
# on method. url and remote_ip keep their *_like indexes for __startswith lookups.
#
# On PostgreSQL the drops run CONCURRENTLY behind lock_timeout, so the deploy fails
# fast instead of blocking inserts; re-run migrate after a timeout. Other backends
# drop the index through the AlterField.

from django.db import migrations, models

from easyaudit.migration_operations import AlterFieldExceptPostgreSQL, PostgreSQLRunSQL

TABLE = 'easyaudit_requestevent'

DROPPED_INDEXES = (
    ('easyaudit_requestevent_method_83a0c884_like', 'method varchar_pattern_ops'),
    ('easyaudit_requestevent_method_83a0c884', 'method'),
)


class Migration(migrations.Migration):

    # CREATE/DROP INDEX CONCURRENTLY cannot run inside a transaction block.
    atomic = False

    dependencies = [
        ('easyaudit', '0019_alter_crudevent_changed_fields_and_more'),
    ]

    operations = [
        PostgreSQLRunSQL(sql="SET lock_timeout = '5s'", reverse_sql='RESET lock_timeout'),
        *(
            PostgreSQLRunSQL(
                sql=f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"',
                reverse_sql=[
                    f'DROP INDEX CONCURRENTLY IF EXISTS "{name}"',
                    f'CREATE INDEX CONCURRENTLY "{name}" ON "{TABLE}" USING btree ({columns})',
                ],
            )
            for name, columns in DROPPED_INDEXES
        ),
        AlterFieldExceptPostgreSQL(
            model_name='requestevent',
            name='method',
            field=models.CharField(max_length=20, verbose_name='Method'),
        ),
        PostgreSQLRunSQL(sql='RESET lock_timeout', reverse_sql="SET lock_timeout = '5s'"),
    ]
