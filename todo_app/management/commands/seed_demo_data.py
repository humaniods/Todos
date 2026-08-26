from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from todo_app.models import (
    Announcement,
    EmployeeProfile,
    Event,
    Holiday,
    Invitation,
    LeaveLedgerEntry,
    LeaveRequest,
    Membership,
    Notification,
    Organization,
    Task,
    TaskComment,
    Team,
)
from todo_app.services import (
    approve_leave_request,
    create_audit_log,
    create_notification,
    create_organization_for_user,
    next_task_key,
    record_task_activity,
)


DEMO_PASSWORD = "Kalios@123"


class Command(BaseCommand):
    help = "Seed a realistic OfficeDiary demo organization with members, tasks, leave, and activity."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEMO_PASSWORD,
            help="Password to assign to all demo users.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]
        owner_user = self._upsert_user(
            username="avatar",
            email="avatar@kalios.com",
            first_name="Avatar",
            last_name="",
            password=password,
        )
        organization, owner_membership = self._upsert_organization(owner_user)
        team = self._upsert_team(organization, owner_membership)

        member_specs = [
            {
                "username": "naina.sharma",
                "email": "naina.sharma@kalios.com",
                "first_name": "Naina",
                "last_name": "Sharma",
                "display_name": "Naina Sharma",
                "employee_code": "KAL-002",
                "designation": "HR Business Partner",
                "department": "HR & Operations",
                "joining_date": date(2025, 2, 3),
                "roles": {"is_hr": True},
            },
            {
                "username": "raghav.verma",
                "email": "raghav.verma@kalios.com",
                "first_name": "Raghav",
                "last_name": "Verma",
                "display_name": "Raghav Verma",
                "employee_code": "KAL-003",
                "designation": "Engineering Manager",
                "department": "Engineering",
                "joining_date": date(2025, 2, 10),
                "roles": {"is_manager": True},
            },
            {
                "username": "isha.rao",
                "email": "isha.rao@kalios.com",
                "first_name": "Isha",
                "last_name": "Rao",
                "display_name": "Isha Rao",
                "employee_code": "KAL-004",
                "designation": "AI Engineer",
                "department": "Engineering",
                "joining_date": date(2025, 3, 3),
            },
            {
                "username": "kabir.singh",
                "email": "kabir.singh@kalios.com",
                "first_name": "Kabir",
                "last_name": "Singh",
                "display_name": "Kabir Singh",
                "employee_code": "KAL-005",
                "designation": "Backend Engineer",
                "department": "Engineering",
                "joining_date": date(2025, 3, 17),
            },
            {
                "username": "meera.joshi",
                "email": "meera.joshi@kalios.com",
                "first_name": "Meera",
                "last_name": "Joshi",
                "display_name": "Meera Joshi",
                "employee_code": "KAL-006",
                "designation": "Frontend Engineer",
                "department": "Engineering",
                "joining_date": date(2025, 4, 7),
            },
            {
                "username": "arjun.nair",
                "email": "arjun.nair@kalios.com",
                "first_name": "Arjun",
                "last_name": "Nair",
                "display_name": "Arjun Nair",
                "employee_code": "KAL-007",
                "designation": "QA Engineer",
                "department": "Engineering",
                "joining_date": date(2025, 4, 21),
            },
            {
                "username": "sana.khan",
                "email": "sana.khan@kalios.com",
                "first_name": "Sana",
                "last_name": "Khan",
                "display_name": "Sana Khan",
                "employee_code": "KAL-008",
                "designation": "DevOps Engineer",
                "department": "Engineering",
                "joining_date": date(2025, 5, 12),
            },
            {
                "username": "vihaan.patel",
                "email": "vihaan.patel@kalios.com",
                "first_name": "Vihaan",
                "last_name": "Patel",
                "display_name": "Vihaan Patel",
                "employee_code": "KAL-009",
                "designation": "Product Designer",
                "department": "Design",
                "joining_date": date(2025, 5, 26),
            },
            {
                "username": "tara.malhotra",
                "email": "tara.malhotra@kalios.com",
                "first_name": "Tara",
                "last_name": "Malhotra",
                "display_name": "Tara Malhotra",
                "employee_code": "KAL-010",
                "designation": "Operations Executive",
                "department": "Operations",
                "joining_date": date(2025, 6, 16),
            },
        ]

        memberships = {"owner": owner_membership}
        for spec in member_specs:
            user = self._upsert_user(
                username=spec["username"],
                email=spec["email"],
                first_name=spec["first_name"],
                last_name=spec["last_name"],
                password=password,
            )
            memberships[spec["username"]] = self._upsert_membership(
                organization=organization,
                user=user,
                display_name=spec["display_name"],
                employee_code=spec["employee_code"],
                designation=spec["designation"],
                department=spec["department"],
                joining_date=spec["joining_date"],
                reporting_manager=owner_membership,
                team=team,
                **spec.get("roles", {}),
            )

        manager_membership = memberships["raghav.verma"]
        hr_membership = memberships["naina.sharma"]
        team.manager = manager_membership
        team.save(update_fields=["manager"])

        owner_membership.display_name = "Avatar"
        owner_membership.reporting_manager = None
        owner_membership.is_employee = True
        owner_membership.is_manager = True
        owner_membership.is_hr = False
        owner_membership.is_owner = True
        owner_membership.active = True
        owner_membership.save(
            update_fields=[
                "display_name",
                "reporting_manager",
                "is_employee",
                "is_manager",
                "is_hr",
                "is_owner",
                "active",
            ]
        )
        EmployeeProfile.objects.update_or_create(
            membership=owner_membership,
            defaults={
                "employee_code": "KAL-001",
                "designation": "CEO",
                "department": "Leadership",
                "joining_date": date(2025, 1, 6),
            },
        )

        hr_membership.reporting_manager = owner_membership
        hr_membership.save(update_fields=["reporting_manager"])
        manager_membership.reporting_manager = owner_membership
        manager_membership.save(update_fields=["reporting_manager"])

        for key, member in memberships.items():
            if key in {"owner", "naina.sharma", "raghav.verma"}:
                continue
            member.reporting_manager = manager_membership
            member.save(update_fields=["reporting_manager"])

        self._seed_pending_invitation(organization, hr_membership, manager_membership, team)
        self._seed_tasks(
            organization=organization,
            team=team,
            owner=owner_membership,
            manager=manager_membership,
            hr=hr_membership,
            employees=memberships,
        )
        self._seed_leave_data(organization, owner_membership, hr_membership, memberships)
        self._seed_calendar(organization, owner_membership, hr_membership, team)
        self._seed_notifications(owner_membership, hr_membership, manager_membership)

        self.stdout.write(self.style.SUCCESS("Demo data ready for KaliOS."))
        self.stdout.write(f"Organization: {organization.name}")
        self.stdout.write(f"Team: {team.name}")
        self.stdout.write(f"Demo password: {password}")
        self.stdout.write("Users: avatar, naina.sharma, raghav.verma, isha.rao, kabir.singh, meera.joshi, arjun.nair, sana.khan, vihaan.patel, tara.malhotra")

    def _upsert_user(self, username, email, first_name, last_name, password):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
            },
        )
        changed = False
        if user.email != email:
            user.email = email
            changed = True
        if user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if user.last_name != last_name:
            user.last_name = last_name
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if created or not user.check_password(password):
            user.set_password(password)
            changed = True
        if changed:
            user.save()
        return user

    def _upsert_organization(self, owner_user):
        organization = Organization.objects.filter(slug="kalios").first()
        if organization:
            organization.name = "KaliOS"
            organization.timezone = "Asia/Kolkata"
            organization.work_week = "Mon-Fri"
            organization.leave_year_start = date(2026, 1, 1)
            organization.created_by = owner_user
            organization.save()
            owner_membership, _ = Membership.objects.get_or_create(
                organization=organization,
                user=owner_user,
                defaults={
                    "display_name": "Avatar",
                    "is_employee": True,
                    "is_manager": True,
                    "is_owner": True,
                },
            )
            return organization, owner_membership
        return create_organization_for_user(
            owner_user,
            "KaliOS",
            "Asia/Kolkata",
            "Mon-Fri",
            date(2026, 1, 1),
        )

    def _upsert_team(self, organization, owner_membership):
        team, _ = Team.objects.update_or_create(
            organization=organization,
            name="The AI Rishis",
            defaults={"manager": owner_membership},
        )
        Team.objects.filter(organization=organization, name="General").exclude(pk=team.pk).delete()
        team.members.add(owner_membership)
        return team

    def _upsert_membership(
        self,
        organization,
        user,
        display_name,
        employee_code,
        designation,
        department,
        joining_date,
        reporting_manager,
        team,
        is_employee=True,
        is_manager=False,
        is_hr=False,
        is_owner=False,
    ):
        membership, _ = Membership.objects.update_or_create(
            organization=organization,
            user=user,
            defaults={
                "display_name": display_name,
                "is_employee": is_employee,
                "is_manager": is_manager,
                "is_hr": is_hr,
                "is_owner": is_owner,
                "reporting_manager": reporting_manager,
                "active": True,
                "deactivated_at": None,
            },
        )
        EmployeeProfile.objects.update_or_create(
            membership=membership,
            defaults={
                "employee_code": employee_code,
                "designation": designation,
                "department": department,
                "joining_date": joining_date,
            },
        )
        team.members.add(membership)
        return membership

    def _seed_pending_invitation(self, organization, hr_membership, manager_membership, team):
        Invitation.objects.update_or_create(
            organization=organization,
            email="next.hire@kalios.com",
            defaults={
                "invited_name": "Next Hire",
                "invited_by": hr_membership,
                "role": "employee",
                "team": team,
                "reporting_manager": manager_membership,
                "token": "kalios-demo-next-hire",
                "expires_at": timezone.now() + timedelta(days=14),
                "accepted_at": None,
            },
        )

    def _seed_tasks(self, organization, team, owner, manager, hr, employees):
        task_specs = [
            {
                "title": "Launch onboarding assistant",
                "description": "Build the first workflow for new employee onboarding FAQs and document suggestions.",
                "task_type": "development",
                "status": "in_progress",
                "progress_stage": "development",
                "priority": "High",
                "primary": employees["isha.rao"],
                "collaborators": [manager, employees["kabir.singh"]],
                "comment": "Initial implementation started and API prompts are being drafted.",
                "start_date": date(2026, 8, 18),
                "due_date": date(2026, 8, 30),
                "expected_next_update": date(2026, 8, 27),
            },
            {
                "title": "Stabilize notification API",
                "description": "Fix intermittent unread counter mismatches between dashboard and notifications page.",
                "task_type": "development",
                "status": "blocked",
                "progress_stage": "qa_testing_pending",
                "blocked_type": "dependency",
                "blocked_reason": "Waiting for staging credentials from infrastructure.",
                "priority": "High",
                "primary": employees["sana.khan"],
                "collaborators": [manager, employees["arjun.nair"]],
                "comment": "Work is blocked until staging access is restored.",
                "start_date": date(2026, 8, 14),
                "due_date": date(2026, 8, 29),
                "expected_next_update": date(2026, 8, 27),
            },
            {
                "title": "Refresh leave dashboard cards",
                "description": "Improve hierarchy and clarity on leave balances, pending requests, and approvals.",
                "task_type": "development",
                "status": "done",
                "progress_stage": "ready_to_close",
                "priority": "Medium",
                "primary": employees["meera.joshi"],
                "collaborators": [manager, employees["vihaan.patel"]],
                "comment": "Design review is complete and the feature is ready to close.",
                "start_date": date(2026, 8, 5),
                "due_date": date(2026, 8, 20),
                "expected_next_update": date(2026, 8, 20),
            },
            {
                "title": "Prepare QA checklist for release 1.3",
                "description": "Collect regression checks for tasks, leave, events, and announcement modules.",
                "task_type": "general",
                "status": "todo",
                "priority": "Medium",
                "primary": employees["arjun.nair"],
                "collaborators": [manager],
                "comment": "Checklist outline created and pending task breakdown.",
                "start_date": date(2026, 8, 25),
                "due_date": date(2026, 9, 1),
                "expected_next_update": date(2026, 8, 28),
            },
            {
                "title": "Document member invitation SOP",
                "description": "Write HR-friendly steps for inviting, onboarding, and activating members in OfficeDiary.",
                "task_type": "general",
                "status": "in_progress",
                "priority": "Low",
                "primary": hr,
                "collaborators": [owner, manager, employees["tara.malhotra"]],
                "comment": "Drafting the first SOP version for demo and onboarding.",
                "start_date": date(2026, 8, 21),
                "due_date": date(2026, 9, 2),
                "expected_next_update": date(2026, 8, 28),
            },
        ]

        existing_tasks = {
            task.title: task for task in organization.tasks.filter(title__in=[spec["title"] for spec in task_specs])
        }
        for spec in task_specs:
            task = existing_tasks.get(spec["title"])
            if task is None:
                task = Task.objects.create(
                    organization=organization,
                    team=team,
                    user=owner.user,
                    primary_assignee=spec["primary"].user,
                    primary_membership=spec["primary"],
                    task_key=next_task_key(organization),
                    title=spec["title"],
                    description=spec["description"],
                    start_date=spec["start_date"],
                    due_date=spec["due_date"],
                    expected_next_update=spec["expected_next_update"],
                    priority=spec["priority"],
                    task_type=spec["task_type"],
                    status=spec["status"],
                    progress_stage=spec.get("progress_stage", ""),
                    blocked_type=spec.get("blocked_type", ""),
                    blocked_reason=spec.get("blocked_reason", ""),
                    blocked_from_stage=spec.get("progress_stage", "") if spec["status"] == "blocked" else "",
                    completion_timestamp=timezone.now() if spec["status"] == "done" else None,
                )
            else:
                for field in [
                    "team",
                    "primary_assignee",
                    "primary_membership",
                    "description",
                    "start_date",
                    "due_date",
                    "expected_next_update",
                    "priority",
                    "task_type",
                    "status",
                    "progress_stage",
                    "blocked_type",
                    "blocked_reason",
                    "blocked_from_stage",
                    "completion_timestamp",
                ]:
                    setattr(
                        task,
                        field,
                        {
                            "team": team,
                            "primary_assignee": spec["primary"].user,
                            "primary_membership": spec["primary"],
                            "description": spec["description"],
                            "start_date": spec["start_date"],
                            "due_date": spec["due_date"],
                            "expected_next_update": spec["expected_next_update"],
                            "priority": spec["priority"],
                            "task_type": spec["task_type"],
                            "status": spec["status"],
                            "progress_stage": spec.get("progress_stage", ""),
                            "blocked_type": spec.get("blocked_type", ""),
                            "blocked_reason": spec.get("blocked_reason", ""),
                            "blocked_from_stage": spec.get("progress_stage", "") if spec["status"] == "blocked" else "",
                            "completion_timestamp": timezone.now() if spec["status"] == "done" else None,
                        }[field],
                    )
                task.save()
            task.collaborators.set([member.user for member in spec["collaborators"]])
            task.collaborator_memberships.set(spec["collaborators"])
            if not task.comments.filter(body=spec["comment"]).exists():
                TaskComment.objects.create(task=task, author=manager.user, body=spec["comment"])
            if not task.activities.filter(
                actor=manager.user,
                from_status="todo",
                to_status=task.status,
                from_progress_stage="",
                to_progress_stage=task.progress_stage,
                comment=spec["comment"],
            ).exists():
                record_task_activity(task, manager.user, "todo", "", spec["comment"])
            self._ensure_audit_log(organization, manager, "task_seeded", task, task.title)

    def _seed_leave_data(self, organization, owner, hr, memberships):
        casual_leave = organization.leave_types.filter(name="Casual leave").first()
        if not casual_leave:
            return

        approved_employee = memberships["tara.malhotra"]
        pending_employee = memberships["kabir.singh"]

        approved_request, created = LeaveRequest.objects.get_or_create(
            organization=organization,
            membership=approved_employee,
            leave_type=casual_leave,
            start_date=date(2026, 8, 26),
            end_date=date(2026, 8, 27),
            defaults={"reason": "Family visit", "status": "pending"},
        )
        if created or approved_request.status != "approved":
            approve_leave_request(approved_request, hr, approve=True, note="Approved for demo data.")

        pending_request, _ = LeaveRequest.objects.update_or_create(
            organization=organization,
            membership=pending_employee,
            leave_type=casual_leave,
            start_date=date(2026, 8, 29),
            end_date=date(2026, 8, 30),
            defaults={"reason": "Personal work", "status": "pending", "approver": None, "approver_note": ""},
        )

        if not LeaveLedgerEntry.objects.filter(
            organization=organization,
            membership=owner,
            leave_type=casual_leave,
            entry_type="hr_correction",
            note="Leadership carry-over adjustment",
        ).exists():
            LeaveLedgerEntry.objects.create(
                organization=organization,
                membership=owner,
                leave_type=casual_leave,
                entry_type="hr_correction",
                days=Decimal("2.0"),
                note="Leadership carry-over adjustment",
                created_by=hr,
            )

        Notification.objects.get_or_create(
            membership=hr,
            category="leave",
            title=f"Pending leave request from {pending_employee.display_name}",
            defaults={
                "body": f"{pending_request.start_date} to {pending_request.end_date}",
                "url": "/leave/admin/",
            },
        )

    def _seed_calendar(self, organization, owner, hr, team):
        Holiday.objects.update_or_create(
            organization=organization,
            name="Ganesh Chaturthi",
            date=date(2026, 9, 12),
            defaults={"location": "India", "description": "Observed company-wide for the India office."},
        )
        Holiday.objects.update_or_create(
            organization=organization,
            name="Quarterly Wellness Day",
            date=date(2026, 10, 2),
            defaults={"location": "Remote", "description": "Recharge day across the organization."},
        )

        event_dt = timezone.make_aware(datetime.combine(date(2026, 8, 28), time(16, 0)))
        event, _ = Event.objects.update_or_create(
            organization=organization,
            title="Sprint 14 Demo",
            defaults={
                "description": "Showcase onboarding, leave, and dashboard improvements.",
                "event_type": "meeting",
                "starts_at": event_dt,
                "location_or_link": "Conference Room A / Meet Link",
                "audience": "teams",
                "created_by": owner,
            },
        )
        event.teams.set([team])

        announcement, _ = Announcement.objects.update_or_create(
            organization=organization,
            title="Welcome to the KaliOS demo workspace",
            defaults={
                "content": "Use this organization to demonstrate onboarding, team structure, tasks, leave, and notifications.",
                "audience": "org",
                "publish_at": timezone.now() - timedelta(hours=2),
                "expiry_at": None,
                "created_by": hr,
            },
        )
        announcement.teams.clear()

    def _seed_notifications(self, owner, hr, manager):
        for membership, title, body, url in [
            (
                owner,
                "Executive overview ready",
                "Dashboard now reflects task, leave, and activity snapshots for the KaliOS demo.",
                "/",
            ),
            (
                hr,
                "Invitation pending",
                "A sample pending invite exists for Next Hire so the member-add flow is visible in demo.",
                "/people/",
            ),
            (
                manager,
                "Team workload updated",
                "The AI Rishis now has mixed task states for walkthroughs.",
                "/tasks/",
            ),
        ]:
            Notification.objects.get_or_create(
                membership=membership,
                category="admin",
                title=title,
                defaults={"body": body, "url": url},
            )

    def _ensure_audit_log(self, organization, actor, action, target, description):
        if organization.audit_logs.filter(
            actor=actor,
            action=action,
            target_type=target.__class__.__name__,
            target_id=target.pk,
            description=description,
        ).exists():
            return
        create_audit_log(organization, actor, action, target, description)
