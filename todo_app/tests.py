from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import TaskForm
from .models import LeaveRequest, LeaveType, Membership, Organization, Task, TaskActivity, TaskComment, Team


class OfficeDiaryBaseTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='pw12345', email='owner@example.com')
        self.hr_user = User.objects.create_user(username='hr', password='pw12345', email='hr@example.com')
        self.other = User.objects.create_user(username='other', password='pw12345', email='other@example.com')
        self.organization = Organization.objects.create(
            name='Acme Office',
            slug='acme-office',
            timezone='Asia/Kolkata',
            work_week='Mon-Fri',
            leave_year_start=timezone.localdate(),
            created_by=self.owner,
        )
        self.owner_membership = Membership.objects.create(
            organization=self.organization,
            user=self.owner,
            display_name='Owner User',
            is_employee=True,
            is_manager=True,
            is_hr=True,
            is_owner=True,
        )
        self.hr_membership = Membership.objects.create(
            organization=self.organization,
            user=self.hr_user,
            display_name='HR User',
            is_employee=True,
            is_hr=True,
        )
        self.other_membership = Membership.objects.create(
            organization=self.organization,
            user=self.other,
            display_name='Other User',
            is_employee=True,
        )
        self.leave_type = LeaveType.objects.create(
            organization=self.organization,
            name='Casual Leave',
            annual_allocation='12.0',
        )
        self.team = Team.objects.create(
            organization=self.organization,
            name='Engineering',
            manager=self.owner_membership,
        )
        self.team.members.add(self.owner_membership, self.hr_membership, self.other_membership)


class TaskWorkflowFormTests(OfficeDiaryBaseTestCase):
    def test_development_task_defaults_to_development_checkpoint(self):
        form = TaskForm(
            membership=self.owner_membership,
            data={
                'team': self.team.pk,
                'title': 'Build roadmap view',
                'description': 'Implement the first pass',
                'priority': 'High',
                'task_type': 'development',
                'primary_assignee': self.owner.pk,
                'collaborators': [self.other.pk],
                'status': 'in_progress',
                'progress_stage': '',
                'blocked_type': '',
                'blocked_reason': '',
                'reopened_reason': '',
                'tags': [],
                'progress_comment': '',
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['progress_stage'], 'development')

    def test_blocked_task_requires_reason_and_comment(self):
        task = Task.objects.create(
            organization=self.organization,
            team=self.team,
            user=self.owner,
            primary_assignee=self.owner,
            primary_membership=self.owner_membership,
            title='Blocked work',
            priority='Medium',
        )
        form = TaskForm(
            membership=self.owner_membership,
            instance=task,
            data={
                'team': self.team.pk,
                'title': task.title,
                'description': '',
                'priority': 'Medium',
                'task_type': 'general',
                'primary_assignee': self.owner.pk,
                'collaborators': [],
                'status': 'blocked',
                'progress_stage': '',
                'blocked_type': '',
                'blocked_reason': '',
                'reopened_reason': '',
                'tags': [],
                'progress_comment': '',
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn('blocked_type', form.errors)
        self.assertIn('blocked_reason', form.errors)
        self.assertIn('progress_comment', form.errors)

    def test_reopening_done_task_requires_reason(self):
        task = Task.objects.create(
            organization=self.organization,
            team=self.team,
            user=self.owner,
            primary_assignee=self.owner,
            primary_membership=self.owner_membership,
            title='Completed work',
            priority='Medium',
            status='done',
        )
        form = TaskForm(
            membership=self.owner_membership,
            instance=task,
            data={
                'team': self.team.pk,
                'title': task.title,
                'description': '',
                'priority': 'Medium',
                'task_type': 'general',
                'primary_assignee': self.owner.pk,
                'collaborators': [],
                'status': 'in_progress',
                'progress_stage': '',
                'blocked_type': '',
                'blocked_reason': '',
                'reopened_reason': '',
                'tags': [],
                'progress_comment': 'Need another pass.',
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn('reopened_reason', form.errors)


class TaskViewsTests(OfficeDiaryBaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='owner', password='pw12345')
        session = self.client.session
        session['active_organization_id'] = self.organization.id
        session.save()

    def test_create_task_records_comment_and_activity(self):
        response = self.client.post(reverse('task-add'), data={
            'team': self.team.pk,
            'title': 'API integration',
            'description': 'Wire the backend',
            'priority': 'High',
            'task_type': 'development',
            'primary_assignee': self.owner.pk,
            'collaborators': [self.other.pk],
            'status': 'in_progress',
            'progress_stage': 'development',
            'blocked_type': '',
            'blocked_reason': '',
            'reopened_reason': '',
            'tags': [],
            'progress_comment': 'Started development checkpoint.',
        })

        self.assertEqual(response.status_code, 302)
        task = Task.objects.get(title='API integration')
        self.assertEqual(task.primary_membership, self.owner_membership)
        self.assertEqual(task.organization, self.organization)
        self.assertEqual(task.comments.count(), 1)
        self.assertEqual(task.activities.count(), 1)

    def test_comment_post_creates_comment_and_activity(self):
        task = Task.objects.create(
            organization=self.organization,
            team=self.team,
            user=self.owner,
            primary_assignee=self.owner,
            primary_membership=self.owner_membership,
            title='Document release',
            priority='Low',
        )

        response = self.client.post(reverse('task-detail', args=[task.pk]), data={'body': 'Release notes drafted.'})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(TaskComment.objects.filter(task=task).count(), 1)
        self.assertEqual(TaskActivity.objects.filter(task=task).count(), 1)

    def test_list_view_shows_collaborative_tasks(self):
        task = Task.objects.create(
            organization=self.organization,
            team=self.team,
            user=self.owner,
            primary_assignee=self.owner,
            primary_membership=self.owner_membership,
            title='Review branch',
            priority='Medium',
        )
        task.collaborators.add(self.other)
        task.collaborator_memberships.add(self.other_membership)

        self.client.logout()
        self.client.login(username='other', password='pw12345')
        session = self.client.session
        session['active_organization_id'] = self.organization.id
        session.save()

        response = self.client.get(reverse('task-list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Review branch')


class LeaveWorkflowTests(OfficeDiaryBaseTestCase):
    def login_as(self, username):
        self.client.logout()
        self.client.login(username=username, password='pw12345')
        session = self.client.session
        session['active_organization_id'] = self.organization.id
        session.save()

    def test_owner_cannot_open_leave_home(self):
        self.login_as('owner')

        response = self.client.get(reverse('leave-home'))

        self.assertEqual(response.status_code, 403)

    def test_owner_can_approve_hr_leave(self):
        leave_request = LeaveRequest.objects.create(
            organization=self.organization,
            membership=self.hr_membership,
            leave_type=self.leave_type,
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
        )
        self.login_as('owner')

        response = self.client.post(reverse('leave-request-decide', args=[leave_request.pk]), data={
            'decision': 'approve',
            'note': 'Approved by CEO.',
        })

        self.assertEqual(response.status_code, 302)
        leave_request.refresh_from_db()
        self.assertEqual(leave_request.status, 'approved')
        self.assertEqual(leave_request.approver, self.owner_membership)

    def test_owner_cannot_approve_employee_leave(self):
        leave_request = LeaveRequest.objects.create(
            organization=self.organization,
            membership=self.other_membership,
            leave_type=self.leave_type,
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
        )
        self.login_as('owner')

        response = self.client.post(reverse('leave-request-decide', args=[leave_request.pk]), data={
            'decision': 'approve',
            'note': 'Should not work.',
        })

        self.assertEqual(response.status_code, 403)
        leave_request.refresh_from_db()
        self.assertEqual(leave_request.status, 'pending')


class DashboardVisibilityTests(OfficeDiaryBaseTestCase):
    def test_hr_dashboard_hides_owner_overview(self):
        self.client.login(username='hr', password='pw12345')
        session = self.client.session
        session['active_organization_id'] = self.organization.id
        session.save()

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'HR Overview')
        self.assertNotContains(response, 'Owner Overview')


class ApiTests(OfficeDiaryBaseTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username='owner', password='pw12345')
        session = self.client.session
        session['active_organization_id'] = self.organization.id
        session.save()

    def test_tasks_api_lists_organization_tasks(self):
        Task.objects.create(
            organization=self.organization,
            team=self.team,
            user=self.owner,
            primary_assignee=self.owner,
            primary_membership=self.owner_membership,
            task_key='ACO-0001',
            title='API visible task',
            priority='Medium',
        )

        response = self.client.get(f'/api/organizations/{self.organization.id}/tasks')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'API visible task')

    def test_member_deactivate_api_offboards_member(self):
        task = Task.objects.create(
            organization=self.organization,
            team=self.team,
            user=self.owner,
            primary_assignee=self.other,
            primary_membership=self.other_membership,
            task_key='ACO-0002',
            title='Transfer me',
            priority='Medium',
        )

        response = self.client.post(
            f'/api/organizations/{self.organization.id}/members/{self.other_membership.id}/deactivate',
            data={'replacement_membership': self.owner_membership.id, 'reason': 'Offboarding test'},
        )

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.other_membership.refresh_from_db()
        self.assertFalse(self.other_membership.active)
        self.assertEqual(task.primary_membership, self.owner_membership)
