from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_existing_tasks(apps, schema_editor):
    Task = apps.get_model('todo_app', 'Task')
    for task in Task.objects.all():
        task.primary_assignee_id = task.user_id
        task.status = 'done' if task.completed else 'todo'
        task.task_type = 'general'
        task.progress_stage = ''
        task.blocked_reason = ''
        task.reopened_reason = ''
        task.save(
            update_fields=[
                'primary_assignee',
                'status',
                'task_type',
                'progress_stage',
                'blocked_reason',
                'reopened_reason',
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('todo_app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='blocked_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='task',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name='task',
            name='primary_assignee',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='primary_tasks',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='task',
            name='progress_stage',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', 'No checkpoint'),
                    ('development', 'Development'),
                    ('self_review', 'Self Review'),
                    ('qa_testing', 'QA Testing'),
                    ('production_testing', 'Production Testing'),
                    ('ready_to_close', 'Ready to Close'),
                ],
                default='',
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name='task',
            name='reopened_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='task',
            name='status',
            field=models.CharField(
                choices=[('todo', 'To Do'), ('in_progress', 'In Progress'), ('blocked', 'Blocked'), ('done', 'Done')],
                default='todo',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='task',
            name='task_type',
            field=models.CharField(choices=[('general', 'General'), ('development', 'Development')], default='general', max_length=20),
        ),
        migrations.AddField(
            model_name='task',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name='task',
            name='collaborators',
            field=models.ManyToManyField(blank=True, related_name='collaborative_tasks', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='TaskComment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('author', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='task_comments', to=settings.AUTH_USER_MODEL)),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='todo_app.task')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='TaskActivity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('from_status', models.CharField(blank=True, max_length=20)),
                ('to_status', models.CharField(blank=True, max_length=20)),
                ('from_progress_stage', models.CharField(blank=True, max_length=30)),
                ('to_progress_stage', models.CharField(blank=True, max_length=30)),
                ('comment', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='task_activities', to=settings.AUTH_USER_MODEL)),
                ('task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activities', to='todo_app.task')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.RunPython(migrate_existing_tasks, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='task',
            name='primary_assignee',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='primary_tasks', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RemoveField(
            model_name='task',
            name='completed',
        ),
    ]
