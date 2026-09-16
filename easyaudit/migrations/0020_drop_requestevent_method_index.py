# NOTE (pipefile fork): easyaudit_requestevent takes an insert on nearly every
# request, so every index on it is maintained on every write. `method` holds a
# handful of distinct values that no hot-path query filters on, so its index and
# its varchar_pattern_ops (*_like) twin are dropped. url and remote_ip keep both of
# theirs: `__startswith` compiles to an unwrapped `col::text LIKE 'prefix%'`, which
# only the *_like index serves under a non-C collation, and remote_ip stores an
# X-Forwarded-For chain that is searched by prefix.
#
# A plain DROP INDEX takes an ACCESS EXCLUSIVE lock, which queues every insert on
# this table behind any open reader. On PostgreSQL the drops are therefore raw
# CONCURRENTLY SQL: non-atomic, one statement per operation, with lock_timeout set
# and reset in operations of their own so the deploy fails fast rather than waits.
# A timed-out drop can leave its index INVALID; re-running migrate completes it
# (IF EXISTS). A reverse drops any leftover index of the same name before
# rebuilding it, so a timed-out reverse is also completed by a re-run. Every other
# backend drops the index through the AlterField itself.

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
