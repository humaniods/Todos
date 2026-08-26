# OfficeDiary

OfficeDiary is a Django-based modular monolith for organization-scoped work management, leave administration, holidays, events, announcements, notifications, and audit activity.

## Included product areas

- Authentication, organization onboarding, and invitations
- Organization memberships with owner, HR, manager, and employee capabilities
- Teams and employee profiles
- General and development task workflows with comments, activity, collaborators, and attachments
- Leave requests, leave types, immutable ledger entries, and HR approval
- Holidays, events, announcements, notifications, and audit trail
- Server-rendered UI and organization-scoped REST API

## Local run

```bash
python manage.py migrate
python manage.py runserver
```

If your shell does not expose `python`, use the venv interpreter directly:

```bash
./.venv/bin/python manage.py migrate
./.venv/bin/python manage.py runserver
```

## Demo data

Seed a reusable demo organization for product walkthroughs:

```bash
./.venv/bin/python manage.py seed_demo_data
```

This creates:

- Organization: `KaliOS`
- Team: `The AI Rishis`
- Members: 1 owner (`Avatar`), 1 HR, 1 manager, 7 employees
- Sample tasks, leave requests, holidays, an event, an announcement, notifications, and a pending invitation

Default demo password for all seeded users:

```text
Kalios@123
```

Seeded usernames:

```text
avatar
naina.sharma
raghav.verma
isha.rao
kabir.singh
meera.joshi
arjun.nair
sana.khan
vihaan.patel
tara.malhotra
```

## Docker

```bash
docker compose up --build
```

## API

Base path: `/api/`

Implemented endpoint groups:

- `/api/auth/*`
- `/api/organizations*`
- `/api/invitations/*`
- `/api/organizations/{org_id}/members*`
- `/api/organizations/{org_id}/teams*`
- `/api/organizations/{org_id}/tasks*`
- `/api/organizations/{org_id}/leave-*`
- `/api/organizations/{org_id}/holidays`
- `/api/organizations/{org_id}/events`
- `/api/organizations/{org_id}/announcements`
- `/api/organizations/{org_id}/dashboard`
- `/api/notifications*`

## Email and password reset

The default email backend is console output. Configure SMTP environment variables in deployment to send real emails.

## Background jobs

Celery is configured through `todo_project/celery.py`. Redis is the default broker and result backend.
