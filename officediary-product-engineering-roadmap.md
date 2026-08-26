# OfficeDiary Product and Engineering Plan

**Version:** 1.1  
**Backend stack:** Python, Django, and Django REST Framework  
**Architecture:** Modular monolith

---

## 1. Executive summary

OfficeDiary is a lightweight, organization-based work management application for small and mid-sized teams. It combines the essential parts of a task tracker with a small HR self-service layer.

The product has one application and one account system, but presents different capabilities according to the member's organization-scoped permissions:

- **CEO/Owner:** organization-wide operational control.
- **HR:** employee directory, leave, holidays, events, and announcements.
- **Manager:** team membership, task assignment, task progress, and workload visibility.
- **Employee:** own tasks, progress updates, leave balance, leave requests, holidays, and events.

Every organization member receives base Employee permissions. Owner, HR, and Manager are additional permission sets, not separate kinds of accounts. This lets an HR member or Manager continue to receive personal tasks and request personal leave.

### Product promise

> A simple office operating system where work is assigned clearly, progress is visible, employees understand their leave, and managers do not need to chase updates.

### V1 boundaries

V1 includes:

- Authentication and organization onboarding.
- Organization-scoped roles and permissions.
- Employee directory, teams, and reporting managers.
- General and Development tasks.
- Kanban board and My Tasks view.
- Structured development checkpoints and progress comments.
- Task comments, collaborators, attachments, and activity history.
- Leave balances, leave requests, company holidays, and HR approval.
- Events and announcements.
- Role-specific dashboards.
- In-app and email notifications.
- Audit trail, Docker deployment, backups, and open-source documentation.

V1 does **not** include:

- Payroll.
- Attendance or biometric integrations.
- Recruitment or applicant tracking.
- Performance reviews.
- Employee monitoring or productivity scores.
- Chat or video calling.
- Wiki or document management.
- Sprints, epics, story points, or custom Jira workflows.
- AI assistants.
- CRM, expenses, invoicing, or asset inventory.

---

## 2. Locked technical decisions

OfficeDiary will use a Python and Django stack.

| Layer | Decision |
|---|---|
| Language | Python |
| Application framework | Django |
| API layer | Django REST Framework |
| Architecture | Modular monolith |
| Database | PostgreSQL |
| Background jobs | Celery with Redis |
| Server-rendered UI | Django templates with HTMX and Alpine.js |
| Styling | Tailwind CSS or an equivalent project-wide design system |
| Kanban interaction | Lightweight drag-and-drop library integrated with HTMX/API commands |
| File storage | S3-compatible storage; MinIO for self-hosting |
| Authentication | Django authentication with secure organization-scoped sessions |
| Internal administration | Django Admin, restricted to trusted system administrators |
| Packaging | Docker and Docker Compose |

The product UI should remain separate from Django Admin. Django Admin is an operational fallback for trusted administrators, not the interface used by CEO, HR, Manager, or Employee.

The backend should expose REST endpoints for important workflows even when the V1 UI is server-rendered. This preserves a clean boundary for future mobile apps, integrations, or a separate frontend without introducing that complexity now.

Existing source code has not yet been reviewed. If a working frontend already exists, preserve it and use Django REST Framework as its backend instead of rewriting it only to match this recommendation.

---

## 3. Product principles

1. **Simple main workflow:** The board always uses To Do, In Progress, Blocked, and Done.
2. **Detail inside the task:** Development checkpoints live inside In Progress instead of becoming additional board columns.
3. **Roles are assigned, never self-declared:** An invited member cannot select CEO or HR during login.
4. **Least-privilege access:** Managers see their teams; HR sees people and leave; employees see themselves; Owner sees organization operations.
5. **One accountable owner per task:** A task has one primary assignee and may have multiple collaborators.
6. **Progress must be explainable:** Important stage changes require a progress comment.
7. **HR data remains private:** Managers see availability, not confidential leave details.
8. **Every important change is auditable:** Roles, task stages, blockers, leave balances, and approvals create immutable activity records.
9. **No artificial self-hosted seat limit:** Lists are paginated and indexed so the application can scale without loading the entire organization into the browser.
10. **No premature platform complexity:** No microservices, plugin marketplace, custom workflow builder, or analytics warehouse in V1.

---

## 4. Organization and permission model

### 4.1 Membership model

A global User may belong to multiple organizations. Access is granted through an Organization Membership.

```text
User
  └── Organization Membership
        ├── Base permission: Employee
        ├── Optional permission: Manager
        ├── Optional permission: HR
        └── Optional permission: Owner
```

The same user may be a Manager in one organization and an Employee in another.

### 4.2 Role capabilities

| Capability | Employee | Manager | HR | Owner/CEO |
|---|---|---|---|---|
| View own profile and tasks | Yes | Yes | Yes | Yes |
| Update own task status and progress | Yes | Yes | Yes | Yes |
| Request leave and view own balance | Yes | Yes | Yes | Yes |
| View public holidays and events | Yes | Yes | Yes | Yes |
| View team members | No | Direct teams | Organization directory | Entire organization |
| Assign tasks | No | Direct team | HR team if also Manager | Anyone |
| View task boards | Own tasks | Direct teams | Own/HR team tasks | All teams |
| Reassign or delete tasks | No | Direct team tasks | Only if also Manager | All tasks |
| Invite employees | No | No in V1 | Yes | Yes |
| Create teams and assign Managers | No | No | Maintain membership only | Yes |
| Grant HR or Manager permission | No | No | No | Yes |
| Grant or remove Owner permission | No | No | No | Owner only |
| Configure leave types and allocations | No | No | Yes | Yes |
| Approve/reject leave | No | Notification only in V1 | Yes | Override |
| Create events and announcements | No | No in V1 | Yes | Yes |
| View organization dashboard | No | Team dashboard | HR dashboard | Full dashboard |
| Manage organization settings | No | No | Limited HR settings | Yes |

### 4.3 Permission invariants

- The first member who creates an organization becomes Owner.
- Public signup never accepts a privileged role value.
- Invitation roles are created by an existing authorized member.
- HR may invite an Employee and assign their team/manager, but cannot grant HR, Manager, or Owner permissions.
- Owner permission changes require an existing Owner.
- An organization must always retain at least one active Owner.
- Authorization is checked in the backend on every read and write.
- A missing permission returns `403`; a cross-organization resource should normally return `404` to avoid information disclosure.

---

## 5. Information architecture

### 5.1 Shared navigation

- Organization switcher.
- Global create button, limited by permission.
- Notification inbox.
- User profile and logout.

### 5.2 Employee navigation

- Home.
- My Tasks.
- Leave.
- Events.
- Profile.

### 5.3 Manager additions

- Team Board.
- Team Members.
- Team Calendar.

### 5.4 HR additions

- People.
- Leave Admin.
- Holidays.
- Events Admin.
- Announcements.

### 5.5 Owner/CEO additions

- Organization Overview.
- All Tasks.
- Teams.
- People.
- Leave Overview.
- Activity.
- Organization Settings.

The frontend should compose navigation from permissions. It should not maintain four unrelated applications or four separate route trees.

---

## 6. Core user journeys

### 6.1 Create an organization

1. User selects **Create an organization**.
2. User signs up with email/password or a supported identity provider.
3. User verifies email.
4. User enters organization name, timezone, work week, and leave year start.
5. System creates Organization and Owner Membership atomically.
6. User creates initial teams or skips this step.
7. User invites HR, Managers, and Employees.
8. User lands on the Owner dashboard with a getting-started checklist.

### 6.2 Join through invitation

1. Authorized member enters email, employee name, team, reporting manager, and permitted role.
2. System creates a time-limited invitation.
3. Recipient opens invitation and signs in or creates an account.
4. Recipient confirms profile details.
5. System creates Organization Membership from the invitation, not from browser-supplied role data.
6. User lands on the dashboard generated from assigned permissions.

### 6.3 Create and complete a general task

1. Manager/Owner creates a General task.
2. Manager sets primary assignee, priority, due date, and description.
3. Employee receives a notification.
4. Employee changes To Do to In Progress.
5. Employee adds progress comments or marks Blocked with a reason.
6. Employee marks Done.
7. Manager may reopen the task with a reason.

### 6.4 Complete a development task

1. Manager/Owner creates a Development task.
2. System initializes `status=TO_DO` and no progress stage.
3. Developer starts the task; system sets `status=IN_PROGRESS` and `progress_stage=DEVELOPMENT`.
4. Developer changes checkpoints using a structured progress update.
5. Each checkpoint change records old stage, new stage, comment, author, and timestamp.
6. QA failure returns the task to Development with a required comment.
7. A blocker preserves the checkpoint from which the task was blocked.
8. Unblocking resumes the saved checkpoint.
9. Production testing pass moves to Ready to Close.
10. Ready to Close may be moved to Done.

### 6.5 Request and approve leave

1. Employee sees Available, Used, and Pending leave.
2. Employee selects leave type and dates.
3. System validates overlap, holidays, and available balance.
4. HR receives a request notification.
5. HR approves or rejects with an optional note.
6. Approval creates a negative leave-ledger entry in the same transaction.
7. Employee and reporting Manager are notified.
8. Team calendar shows the employee as unavailable without exposing a confidential reason.

### 6.6 Publish an event or announcement

1. HR/Owner selects Event or Announcement.
2. Author selects entire organization or specific teams.
3. Author adds date/time, location/link, description, and optional attachment.
4. System publishes immediately or at a scheduled time.
5. Eligible members receive an in-app notification and optional email.

### 6.7 Offboard a member

1. HR initiates deactivation.
2. System shows open tasks owned by the member and any teams they manage.
3. HR/Owner selects replacement assignees and Manager.
4. System transfers work and deactivates Membership.
5. Historical comments, task activity, and approvals preserve the former member's display name.
6. Sessions are revoked and the action is added to the audit log.

---

## 7. Task management specification

### 7.1 Main task statuses

```text
TO_DO → IN_PROGRESS → DONE
            ↕
         BLOCKED

DONE → IN_PROGRESS only through Reopen
```

Board columns remain fixed in V1:

1. To Do.
2. In Progress.
3. Blocked.
4. Done.

### 7.2 Task types

#### General

- Uses only main statuses.
- Suitable for HR, operations, marketing, administration, and normal office tasks.

#### Development

- Uses main statuses plus structured `progress_stage` while In Progress.
- Suitable for software engineering and deployment work.

### 7.3 Development checkpoints

```text
DEVELOPMENT
  → DEV_DEPLOYMENT_PENDING
  → QA_TESTING_PENDING
  → PRODUCTION_DEPLOYMENT_PENDING
  → PRODUCTION_TESTING_PENDING
  → READY_TO_CLOSE
  → DONE
```

Transition rules:

- Starting a Development task selects Development.
- QA pass moves QA Testing Pending to Production Deployment Pending.
- QA failure returns to Development and requires a comment.
- Production testing failure returns to Development and requires a comment.
- Development tasks cannot move to Done unless the stage is Ready to Close, except an Owner override with a required reason.
- Moving to Blocked requires blocker type and reason.
- Blocking stores `blocked_from_stage`.
- Unblocking restores `blocked_from_stage` and clears the active blocker.
- Reopening a Development task returns to Development unless the Manager selects another valid checkpoint.

### 7.4 Task fields

Required:

- Organization.
- Task key, generated per organization.
- Task type.
- Title.
- Status.
- Creator.
- Primary assignee.
- Team.
- Priority.
- Due date.
- Created and updated timestamps.

Optional:

- Description.
- Progress stage.
- Collaborators.
- Start date.
- Blocker type/reason.
- Expected next update.
- Links and attachments.
- Completion timestamp.

### 7.5 Structured progress update

When changing a Development checkpoint, show:

- Current status.
- Current checkpoint.
- New checkpoint.
- Required progress comment.
- Optional expected next update date.
- Optional link or attachment.

The current checkpoint is a structured field. The comment explains the checkpoint. Comments alone must not be used as the source of current status because they cannot reliably power filters, dashboards, or reports.

### 7.6 Task visibility

- Employee: tasks assigned to them or on which they are a collaborator.
- Manager: tasks belonging to their managed teams.
- HR: only tasks available through Employee/Manager permissions; HR does not automatically see all work.
- Owner: all organization tasks.

### 7.7 Task board filters

MVP filters:

- Assignee.
- Team.
- Main status.
- Development checkpoint.
- Priority.
- Due state: overdue, due today, upcoming.
- General or Development task type.

---

## 8. Leave, holiday, and event specification

### 8.1 Leave balance model

Never store leave balance as a manually overwritten number. Calculate it from immutable ledger entries.

Ledger entry examples:

- Annual allocation: `+18`.
- Carry forward: `+3`.
- Approved leave: `-2`.
- Cancellation reversal: `+2`.
- HR correction: `+1` or `-1`, with required reason.

Displayed values:

- Allocated.
- Available.
- Used.
- Pending approval.

### 8.2 Leave types

Initial defaults:

- Casual leave.
- Sick leave.
- Earned/annual leave.
- Unpaid leave.

HR can configure name, unit, annual allocation, carry-forward behavior, and whether a reason is mandatory.

### 8.3 Leave request states

```text
PENDING → APPROVED
        → REJECTED
PENDING/APPROVED → CANCELLED, subject to policy
```

V1 approval model:

- HR approves or rejects.
- Manager is notified and sees availability.
- Owner can override with a mandatory audit reason.

Post-MVP option:

- Configurable Manager approval followed by HR finalization.

### 8.4 Company holidays

Holidays are independent of employee leave.

Fields:

- Name.
- Date.
- Applicable locations or entire organization.
- Optional description.

A company holiday is excluded from charged leave days.

### 8.5 Events and announcements

Events:

- Title, description, type, date/time, location/link, audience, and attachment.

Announcements:

- Title, content, audience, publish time, expiry time, and optional acknowledgement in a later release.

---

## 9. Role-specific dashboards

### 9.1 Employee dashboard

- Tasks due today.
- Overdue tasks.
- Recently assigned tasks.
- Current Development checkpoint when applicable.
- Leave Available, Used, and Pending.
- Upcoming holidays and events.
- Latest announcements.

### 9.2 Manager dashboard

- Team tasks grouped by main status.
- Development tasks grouped by checkpoint.
- Blocked and overdue tasks.
- Member-level active-task count.
- Team members currently unavailable.
- Upcoming deadlines.

Do not create a productivity score or employee ranking in V1.

### 9.3 HR dashboard

- Active employee count.
- Pending leave requests.
- Employees unavailable today.
- Upcoming company holidays.
- Upcoming events and scheduled announcements.
- Recent joins/deactivations.

### 9.4 Owner/CEO dashboard

- Active employees and teams.
- Organization task counts by main status.
- Development task counts by checkpoint.
- Overdue and blocked task counts.
- Team-level completion overview.
- Organization leave overview without unnecessary confidential details.
- Upcoming events and recent administrative activity.

---

## 10. Notification plan

### 10.1 Notification channels

- In-app notification center: MVP.
- Transactional email: MVP.
- Slack, Teams, push notifications, and SMS: post-MVP.

### 10.2 MVP notification events

- Organization invitation.
- Task assigned or reassigned.
- User added as collaborator.
- Mention in task comment.
- Task marked Blocked.
- Task reopened.
- Development checkpoint changed.
- Task due tomorrow or overdue.
- Leave request submitted.
- Leave approved, rejected, or cancelled.
- New holiday.
- New event or announcement for the member's audience.

### 10.3 Noise controls

- Do not email on every ordinary comment unless the user is mentioned.
- Deduplicate repeated events.
- Store read/unread state.
- Allow basic per-category preferences after V1; maintain safe transactional defaults in MVP.

---

## 11. Recommended system architecture

### 11.1 Architecture style

Use a **modular monolith** for V1.

Recommended modules:

```text
accounts
organizations
people
tasks
leave
events
notifications
audit
```

Each module owns its domain logic but runs in one deployable backend and one relational database.

Do not split authentication, tasks, leave, or notifications into microservices before real scaling or team-ownership pressure exists.

### 11.2 Django application structure

Recommended Django apps:

```text
apps/
  accounts/
  organizations/
  people/
  tasks/
  leave/
  events/
  notifications/
  audit/
```

Recommended responsibility split:

- **Models:** persistence structure and database constraints.
- **Services:** task transitions, invitations, leave approvals, role changes, and other write workflows.
- **Selectors:** organization-scoped read queries.
- **Permissions:** reusable object-level permission checks.
- **API serializers/views:** transport validation and response formatting.
- **Tasks:** Celery jobs for email, reminders, and scheduled publication.
- **Templates/components:** role-aware product interface.

Do not place task-transition or leave-ledger logic directly inside views. Keep it in transactional domain services so the same rules apply to the web UI, REST API, Django Admin actions, and background jobs.

### 11.3 Supporting infrastructure

- Database: PostgreSQL.
- Background jobs and broker: Celery with Redis.
- Attachments: S3-compatible storage; MinIO for self-hosting.
- Email: provider abstraction with SMTP support for self-hosters.
- Packaging: Docker Compose for local and self-hosted deployment.
- Reverse proxy and TLS: deployment-layer configuration.

### 11.4 Multi-tenancy

Use a shared database with strict `organization_id` scoping in V1.

Rules:

- Every organization-owned row carries `organization_id`.
- Composite uniqueness includes organization where appropriate.
- Repository/query services require organization context.
- Object authorization validates membership plus permission plus object scope.
- High-risk queries receive explicit multi-tenant isolation tests.

### 11.5 Scalability baseline

Product policy may allow unlimited seats, but the system should use explicit engineering targets.

V1 targets:

- 10,000 members in one organization without loading them all in a single response.
- 100,000 historical tasks per organization with indexed filters.
- Pagination on members, tasks, comments, activities, and notifications.
- Background delivery for email and due-date reminders.
- Attachment uploads directly to object storage using short-lived signed operations.

---

## 12. Data model

### 12.1 Identity and organization

```text
users
organizations
organization_memberships
roles
membership_roles
invitations
teams
team_memberships
employee_profiles
```

Important fields:

- `organization_memberships`: user, organization, status, joined_at, deactivated_at.
- `membership_roles`: membership, role.
- `employee_profiles`: membership, employee_code, designation, department, reporting_manager, joining_date.
- `teams`: organization, name, manager_membership.

### 12.2 Tasks

```text
tasks
task_collaborators
task_updates
task_comments
task_attachments
task_activity
```

Important `tasks` fields:

- organization.
- task_number and generated key.
- task_type.
- title and description.
- status.
- progress_stage.
- blocked_from_stage.
- blocked_reason.
- creator_membership.
- assignee_membership.
- team.
- priority.
- start_date and due_date.
- completed_at.
- created_at and updated_at.

Important `task_updates` fields:

- task.
- actor_membership.
- old_status/new_status.
- old_stage/new_stage.
- update_type.
- comment.
- expected_next_update.
- created_at.

### 12.3 Leave

```text
leave_types
leave_policies
leave_allocations
leave_ledger_entries
leave_requests
company_holidays
```

Approval and ledger mutation must be one database transaction.

### 12.4 Communication and operations

```text
events
announcements
notifications
audit_events
```

Audit events should record actor, organization, action, object type/id, safe metadata, timestamp, and request correlation identifier.

### 12.5 Required indexes

At minimum:

- Membership by `(organization_id, user_id, status)`.
- Task by `(organization_id, status, due_date)`.
- Task by `(organization_id, team_id, status)`.
- Task by `(organization_id, assignee_id, status)`.
- Development task by `(organization_id, progress_stage)`.
- Task activity by `(task_id, created_at)`.
- Leave request by `(organization_id, status, created_at)`.
- Notification by `(membership_id, read_at, created_at)`.

---

## 13. API roadmap

Endpoint names may follow the existing code style; the important requirement is organization scope and object-level authorization.

### 13.1 Authentication and organization

```text
POST   /auth/signup
POST   /auth/login
POST   /auth/logout
POST   /auth/forgot-password
POST   /auth/reset-password

POST   /organizations
GET    /organizations
GET    /organizations/{org_id}
PATCH  /organizations/{org_id}

POST   /organizations/{org_id}/invitations
POST   /invitations/{token}/accept
GET    /organizations/{org_id}/members
PATCH  /organizations/{org_id}/members/{member_id}
POST   /organizations/{org_id}/members/{member_id}/deactivate
```

### 13.2 Teams

```text
GET    /organizations/{org_id}/teams
POST   /organizations/{org_id}/teams
GET    /organizations/{org_id}/teams/{team_id}
PATCH  /organizations/{org_id}/teams/{team_id}
POST   /organizations/{org_id}/teams/{team_id}/members
DELETE /organizations/{org_id}/teams/{team_id}/members/{member_id}
```

### 13.3 Tasks

```text
GET    /organizations/{org_id}/tasks
POST   /organizations/{org_id}/tasks
GET    /organizations/{org_id}/tasks/{task_id}
PATCH  /organizations/{org_id}/tasks/{task_id}
POST   /organizations/{org_id}/tasks/{task_id}/updates
POST   /organizations/{org_id}/tasks/{task_id}/comments
POST   /organizations/{org_id}/tasks/{task_id}/block
POST   /organizations/{org_id}/tasks/{task_id}/unblock
POST   /organizations/{org_id}/tasks/{task_id}/complete
POST   /organizations/{org_id}/tasks/{task_id}/reopen
POST   /organizations/{org_id}/tasks/{task_id}/collaborators
```

Stage transitions should be commands/domain operations, not unrestricted writes to arbitrary status strings.

### 13.4 Leave and holidays

```text
GET    /organizations/{org_id}/leave-types
POST   /organizations/{org_id}/leave-types
GET    /organizations/{org_id}/leave-balances/me
POST   /organizations/{org_id}/leave-requests
GET    /organizations/{org_id}/leave-requests
POST   /organizations/{org_id}/leave-requests/{request_id}/approve
POST   /organizations/{org_id}/leave-requests/{request_id}/reject
POST   /organizations/{org_id}/leave-requests/{request_id}/cancel
POST   /organizations/{org_id}/leave-ledger/adjustments
GET    /organizations/{org_id}/holidays
POST   /organizations/{org_id}/holidays
```

### 13.5 Events, dashboards, and notifications

```text
GET    /organizations/{org_id}/events
POST   /organizations/{org_id}/events
GET    /organizations/{org_id}/announcements
POST   /organizations/{org_id}/announcements

GET    /organizations/{org_id}/dashboard
GET    /organizations/{org_id}/teams/{team_id}/dashboard

GET    /notifications
POST   /notifications/{notification_id}/read
POST   /notifications/read-all
```

---

## 14. Implementation phases

### Phase 1 — Product foundation and delivery setup

Deliverables:

- Final V1 product requirements.
- Permission matrix and organization model.
- General and Development task transition rules.
- Leave ledger and approval rules.
- Low-fidelity wireframes for every role.
- Design tokens and component inventory.
- Repository structure, development environment, code quality, and CI baseline.
- Initial database schema and API contract.
- Seed/demo organization specification.

Exit criteria:

- Every V1 screen maps to a role and permission.
- Every task/leave transition has explicit allowed actors.
- No unresolved P0 product decision remains.

### Phase 2 — Authentication, organizations, and RBAC

Backend:

- User authentication and secure session/token handling.
- Email verification and password reset.
- Organization creation transaction.
- Organization Membership and additive roles.
- Invitation creation, expiry, and acceptance.
- Permission service/middleware.
- Organization-scoped repository/query pattern.
- Audit event foundation.

Frontend:

- Sign up, login, forgot-password, and reset flows.
- Create organization onboarding.
- Accept invitation journey.
- Permission-composed navigation.
- Organization switcher.

Exit criteria:

- A user cannot self-select Owner, HR, or Manager.
- Cross-organization access tests pass.
- Invited user lands on the correct dashboard shell.
- An organization cannot lose its final active Owner.

Milestone: **v0.1 Platform Alpha**.

### Phase 3 — People, teams, and organization administration

Backend:

- Employee profiles.
- Team CRUD.
- Team membership and reporting Manager.
- Member directory with search and pagination.
- Role assignment controlled by Owner.
- Member deactivation and session revocation.
- Task-transfer contract for later offboarding integration.

Frontend:

- People list and employee profile.
- Teams list and team details.
- Invite-member flow.
- Role, team, and Manager assignment UI.
- Owner settings foundation.

Exit criteria:

- Owner can construct a multi-team organization.
- HR can maintain employee metadata without granting privileged roles.
- Manager sees only direct teams.

### Phase 4 — General task management

Backend:

- Task keys and CRUD.
- General task transitions.
- Primary assignee and team scope.
- Comments, attachments, collaborators, and activity log.
- To Do/In Progress/Blocked/Done commands.
- Block/unblock and reopen rules.
- Filtering, sorting, and pagination.
- Assignment and mention notifications.

Frontend:

- My Tasks list.
- Team Kanban board.
- Task create/edit/detail experiences.
- Drag/drop or explicit status transitions with permission checks.
- Comments, attachments, collaborators, and activity timeline.
- Filters for team, assignee, status, priority, and due state.

Exit criteria:

- Manager can create and assign a task without unnecessary configuration.
- Employee starts, blocks, unblocks, comments, and completes a task.
- Employee cannot reassign/delete a managed task.
- Manager and Owner can reopen with a recorded reason.

Milestone: **v0.2 Task Alpha**.

### Phase 5 — Development workflow and structured progress

Backend:

- Development task type.
- Progress-stage state machine.
- Structured progress updates.
- Required comment validation.
- QA/production failure loops.
- Blocked-from-stage preservation and resume.
- Development checkpoint filters and aggregates.

Frontend:

- General/Development task selection.
- Development checkpoint badge on cards.
- Update Progress modal.
- Required blocker/failure forms.
- Manager filters for each checkpoint.
- Timeline entries showing old/new stage and comment.

Exit criteria:

- A Manager can distinguish development, QA pending, production deployment pending, and production testing pending without reading every comment.
- Every checkpoint transition is present in task history.
- Done is rejected before Ready to Close unless an authorized override supplies a reason.

### Phase 6 — Leave and company holidays

Backend:

- Leave types and policies.
- Ledger entries and balance computation.
- Leave request validation.
- HR approval/rejection transaction.
- Cancellation and reversal.
- HR manual adjustment with required reason.
- Company holidays and working-day calculation.

Frontend:

- Employee leave summary and request form.
- Leave request history.
- HR pending requests.
- Approval/rejection interaction.
- HR allocation/adjustment interaction.
- Holiday calendar.

Exit criteria:

- Concurrent approval cannot double-deduct leave.
- Company holidays are excluded correctly.
- Employees cannot see other members' balances or confidential reasons.
- Manager sees availability only.

### Phase 7 — Events, announcements, and notifications

Backend:

- Event and announcement models.
- Organization/team audience resolution.
- In-app notifications.
- Background transactional email.
- Due-date reminder scheduler.
- Notification deduplication.

Frontend:

- Event/announcement administration.
- Employee events view.
- Dashboard announcement area.
- Notification inbox and unread count.

Exit criteria:

- Only audience members can retrieve an event or announcement.
- Important task, leave, and event notifications work end-to-end.
- Ordinary comments do not create unnecessary email spam.

### Phase 8 — Role dashboards and private beta

Backend:

- Employee dashboard aggregates.
- Manager/team aggregates.
- HR aggregates.
- Owner organization aggregates.
- Cache only where measurement shows a need.

Frontend:

- Role-composed dashboard.
- Team task status and checkpoint summaries.
- Blocked/overdue panels.
- Leave and event summaries.
- Empty states and onboarding prompts.

Exit criteria:

- Each role sees only actionable, permitted information.
- No confidential leave reason appears on Manager/Owner summary views.
- Private beta can complete all core journeys without admin shell access.

Milestone: **v0.5 Private Beta**.

### Phase 9 — Security, quality, and performance hardening

- Complete unit, integration, permission, and end-to-end test suites.
- Cross-tenant attack tests.
- File validation and signed attachment access.
- Rate limits for login, invitations, comments, and uploads.
- Query/index review and N+1 elimination.
- Accessibility and responsive-layout pass.
- Audit-log review.
- Backup and restore rehearsal.
- Dependency and secret scanning.

Exit criteria:

- P0/P1 defects closed.
- Organization isolation suite passes.
- Restore rehearsal succeeds.
- Performance targets pass against seeded production-like data.

### Phase 10 — Stable V1 and open-source release

- Production deployment and migration runbook.
- Docker Compose quickstart.
- Environment-variable reference.
- Demo organization and seed data.
- Admin/operator documentation.
- End-user quickstart by role.
- README, CONTRIBUTING, SECURITY, Code of Conduct, and issue templates.
- Changelog and semantic release tagging.
- Final smoke test and rollback rehearsal.

Milestone: **v1.0 Stable**.

---

## 15. Implementation dependency order

| Order | Phase | Depends on | Required outcome |
|---:|---|---|---|
| 1 | Product foundation | Approved scope | Permission matrix, workflows, wireframes, schema, and API contract |
| 2 | Authentication and RBAC | Product foundation | Secure organizations, invitations, memberships, and backend authorization |
| 3 | People and teams | Authentication and RBAC | Employee directory, reporting hierarchy, and team ownership |
| 4 | General tasks | People and teams | Assignable tasks, board, comments, blockers, and history |
| 5 | Development workflow | General tasks | Structured checkpoints, required updates, QA/prod loops, and checkpoint reporting |
| 6 | Leave and holidays | People and teams plus RBAC | Ledger-derived balances, requests, HR approval, and holiday calendar |
| 7 | Events and notifications | Organizations, people, and background jobs | Audience-controlled communication and actionable notifications |
| 8 | Role dashboards | Tasks, leave, events, and permissions | Employee, Manager, HR, and Owner operational views |
| 9 | Hardening | All V1 workflows | Security, permission, reliability, performance, accessibility, backup, and restore validation |
| 10 | Stable release | Hardening | Deployable product, operator docs, user docs, and open-source project material |

Phases express dependency and implementation order only. The project owner decides when a phase begins, how work is divided, and how much capacity is assigned.

---

## 16. Testing strategy

### 16.1 Unit tests

- Task state machine.
- Development checkpoint transition validation.
- Block/unblock resume behavior.
- Role permission predicates.
- Leave working-day calculation.
- Leave ledger balance computation.
- Notification audience resolution.

### 16.2 Integration tests

- Create organization and Owner atomically.
- Accept invitation with server-assigned roles.
- Owner/HR/Manager/Employee permission boundaries.
- Cross-organization resource access.
- Task assignment and notification.
- Structured progress update and activity history.
- Concurrent leave approval.
- Member deactivation and work transfer.

### 16.3 End-to-end journeys

1. Owner creates organization and invites HR/Manager/Employee.
2. Manager assigns General task; Employee completes it.
3. Manager assigns Development task; Developer advances checkpoints.
4. Developer blocks and resumes at the saved checkpoint.
5. QA failure returns task to Development.
6. Employee requests leave; HR approves; Manager sees availability.
7. HR publishes event; only intended audience receives it.
8. HR deactivates Employee after transferring work.

### 16.4 Performance tests

Seed at least:

- 10,000 members.
- 100 teams.
- 100,000 tasks.
- 1,000,000 task activity rows.
- 100,000 notifications.

Initial service requirements:

- Paginated reads remain responsive under expected organization load.
- Ordinary writes do not wait for email delivery.
- Board responses never return unbounded tasks.
- Email and reminder jobs do not block interactive requests.
- Exact performance budgets are set from measured deployment conditions rather than guessed in the product plan.

---

## 17. Security and privacy requirements

### Authentication

- Email verification.
- Secure password hashing or a trusted identity provider.
- HttpOnly, Secure cookies for browser sessions where applicable.
- CSRF protection for cookie-authenticated writes.
- Short-lived invitation and password-reset tokens.
- Session revocation on deactivation and sensitive role changes.
- Rate limiting and suspicious-login logging.

### Authorization

- Deny by default.
- Permission checks on every API operation.
- Object-level organization and team checks.
- No client-selected privileged roles.
- No trusting hidden frontend fields.
- Automated role-matrix tests.

### HR privacy

- Restrict leave reasons and supporting documents.
- Manager and Owner dashboards receive minimum operational information.
- Record who viewed or changed sensitive leave data if such documents are introduced.
- Define retention and deletion policy before collecting additional personal data.

### Attachments

- File type and size allowlist.
- Generated storage keys, not user-controlled paths.
- Signed access with authorization.
- Malware scanning when deployment capability permits.
- No public bucket by default.

### Operations

- Daily encrypted database backups.
- Tested restore process.
- Secret management outside source control.
- Structured logs without confidential leave reasons or tokens.
- Error monitoring, uptime monitoring, and job-queue monitoring.

---

## 18. CI/CD and deployment roadmap

### Pull request checks

- Formatter and linter.
- Static type checks where used.
- Unit and integration tests.
- Migration consistency check.
- Permission test suite.
- Dependency/security scanning.
- Frontend build.

### Environments

- Local: Docker Compose with application, PostgreSQL, Redis, and MinIO/SMTP test service as needed.
- Staging: production-like configuration and anonymized/seeded data.
- Production: managed or self-hosted deployment with documented backup and rollback.

### Deployment rules

- Backward-compatible migrations where possible.
- Database backup before risky migrations.
- Health/readiness checks.
- Release version and changelog.
- Smoke test after deploy.
- Rollback plan tested before V1.

---

## 19. Open-source release plan

Required repository material:

- Clear README with screenshots and product scope.
- One-command local quickstart.
- `.env.example` without secrets.
- Architecture overview.
- Database migration and seed instructions.
- CONTRIBUTING guide.
- Code of Conduct.
- SECURITY policy and private vulnerability reporting route.
- Issue and pull-request templates.
- Public roadmap and changelog.
- Demo data that contains no real employee information.

License decision:

- **AGPL-3.0:** stronger protection against unshared hosted forks.
- **Apache-2.0/MIT:** lower adoption friction and broader commercial reuse.

Choose the license from the intended business model rather than changing it casually after community adoption.

Recommended commercial direction:

- Self-hosted core: no artificial member limit.
- Managed cloud: charge by organization/resource usage rather than per-seat taxation.
- Paid value: managed operations, support, SLA, advanced compliance, SSO/SCIM, longer audit retention, and high availability.

---

## 20. Post-V1 roadmap

### V1.1 — Operational quality

- Recurring tasks.
- Task templates.
- Saved filters.
- Due-date reminder preferences.
- CSV member/task export and import.
- Configurable Manager-first leave approval.
- Event reminders.
- Better offboarding and task transfer.
- PWA/mobile usability improvements.

### V1.2 — Team planning

- Calendar view for tasks and leave.
- Basic team capacity view.
- Project/grouping layer without Jira complexity.
- Custom Development checkpoint templates at organization level.
- Basic public API tokens and webhooks.
- Slack/Teams notification integration.
- Read-only stakeholder/guest access if demand is proven.

### V2 — Enterprise and scale, based on demand

- SSO and SCIM.
- Audit export and configurable retention.
- Multiple office locations and holiday calendars.
- Advanced leave policies and accruals.
- Custom roles/permissions.
- High-availability deployment guidance.
- Admin analytics and organization health.
- Optional manager workload planning.

Explicitly require new validation before adding payroll, attendance, recruitment, performance scoring, chat, or AI.

---

## 21. Product success metrics

### Activation

- Organization onboarding completed without administrator assistance.
- First member invited during initial session.
- First task assigned during initial session.

### Task management

- Task creation completed without unnecessary configuration steps.
- Progress updates completed from the task view without navigating through administration screens.
- Percentage of active Development tasks with a current structured checkpoint.
- Percentage of Blocked tasks with reason and expected owner/action.

### HR self-service

- Percentage of employees who can see accurate leave balance without asking HR.
- Leave request approval turnaround time.
- Leave-balance correction rate.

### Reliability

- Failed notification jobs.
- Permission-denied anomalies and cross-tenant test failures.
- Backup success and restore-test success.
- P95 API latency and error rate.

Do not use employee task counts as a simplistic performance score.

---

## 22. Major risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| User self-selects a privileged role | Organization takeover | Server-assigned invitation roles; Owner-only privilege changes |
| Missing organization filter | Cross-company data leak | Required organization context, repository patterns, isolation tests |
| Task comments used as status | Managers cannot filter/report progress | Structured checkpoint plus explanatory comment |
| Too many board columns | Product becomes another heavy Jira | Four fixed main columns; checkpoints inside In Progress |
| Leave balance overwritten manually | Incorrect entitlement and poor auditability | Immutable leave ledger and transactional approval |
| HR sees all task data by default | Privacy and permission confusion | Additive roles; HR receives task access only through Employee/Manager scope |
| Notification spam | Users disable/ignore notifications | Event selection, deduplication, mention-only comment emails |
| Unlimited-member promise becomes unbounded queries | Performance failures | Pagination, indexes, background processing, explicit scale targets |
| Scope expands into full HRMS | Delayed launch | V1 exclusions and change-control review |
| “Asset” used for employees | Confusing/dehumanizing terminology | Use Employee/Team Member; reserve Asset for equipment |

---

## 23. Definition of Done for V1

V1 is complete only when:

- Owner, HR, Manager, and Employee journeys work end-to-end.
- Privileged roles cannot be self-selected.
- Cross-organization isolation tests pass.
- General and Development task workflows enforce valid transitions.
- Structured progress updates and blocker history are auditable.
- Leave balance is ledger-derived and concurrent approval-safe.
- Role dashboards expose only permitted data.
- Email/in-app notifications work for P0 events.
- Backup and restore have been rehearsed.
- Production deployment and rollback are documented.
- Docker quickstart and open-source contribution/security documentation are available.
- No P0/P1 defect remains open.

---

## 24. Immediate next actions

1. Confirm whether the existing repository uses Django, FastAPI, Node, or another stack.
2. Confirm implementation team size and availability.
3. Product spelling finalized as OfficeDiary (previously OfficeDairy).
4. Turn the Phase 1 requirements into screen wireframes.
5. Create the permission test matrix before feature code.
6. Create database migrations for organizations, memberships, roles, and teams.
7. Implement organization creation and invitation flow before building task UI.
8. Publish the V1 exclusions in the repository roadmap to prevent scope drift.
