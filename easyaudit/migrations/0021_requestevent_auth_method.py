# NOTE (pipefile fork): a nullable column with no default is a catalogue-only change on
# PostgreSQL, so the table is not rewritten. It still needs a brief ACCESS EXCLUSIVE
# lock; lock_timeout makes the deploy fail fast instead of queueing inserts behind it.
# Re-run migrate after a timeout.

from django.db import migrations, models

from easyaudit.migration_operations import PostgreSQLRunSQL


class Migration(migrations.Migration):

    dependencies = [
        ('easyaudit', '0020_drop_requestevent_method_index'),
    ]

    operations = [
        PostgreSQLRunSQL(sql="SET lock_timeout = '5s'", reverse_sql='RESET lock_timeout'),
        migrations.AddField(
            model_name='requestevent',
            name='auth_method',
            field=models.CharField(
                blank=True, max_length=32, null=True, verbose_name='Auth method'
            ),
        ),
        PostgreSQLRunSQL(sql='RESET lock_timeout', reverse_sql="SET lock_timeout = '5s'"),
    ]
