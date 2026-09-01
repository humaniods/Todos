from collections import Counter
from datetime import date

import streamlit as st

from todo_app.streamlit_support import (
    available_leave_types,
    blocker_labels,
    create_task,
    decide_leave,
    ensure_demo_ready,
    organization_snapshot,
    overdue_tasks,
    progress_stage_labels,
    submit_leave,
    task_status_labels,
    upcoming_task_window,
    update_task,
)


st.set_page_config(
    page_title='OfficeDiary Live',
    page_icon='OK',
    layout='wide',
    initial_sidebar_state='expanded',
)

st.markdown(
    """
    <style>
    :root {
        --canvas: #f3efe6;
        --surface: rgba(255, 252, 245, 0.92);
        --ink: #1f2933;
        --muted: #52606d;
        --line: rgba(15, 118, 110, 0.15);
        --accent: #0f766e;
        --accent-2: #d97706;
    }
    .stApp {
        background:
            radial-gradient(circle at top left, rgba(15, 118, 110, 0.14), transparent 30%),
            radial-gradient(circle at top right, rgba(217, 119, 6, 0.16), transparent 28%),
            linear-gradient(180deg, #f8f3ea 0%, var(--canvas) 100%);
        color: var(--ink);
    }
    .hero {
        background: linear-gradient(135deg, rgba(255,255,255,0.82), rgba(223,233,228,0.88));
        border: 1px solid var(--line);
        border-radius: 24px;
        padding: 1.4rem 1.5rem;
        box-shadow: 0 18px 40px rgba(31, 41, 51, 0.08);
        margin-bottom: 1rem;
    }
    .hero h1 {
        margin: 0;
        font-size: 2.2rem;
        letter-spacing: -0.03em;
    }
    .hero p {
        margin: 0.5rem 0 0;
        color: var(--muted);
        max-width: 52rem;
    }
    .metric-card {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 20px;
        padding: 1rem 1.1rem;
        min-height: 132px;
        box-shadow: 0 12px 32px rgba(31, 41, 51, 0.05);
    }
    .metric-label {
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.12em;
        font-size: 0.75rem;
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 700;
        margin: 0.35rem 0 0.15rem;
    }
    .metric-note {
        color: var(--muted);
        font-size: 0.95rem;
    }
    .pill {
        display: inline-block;
        padding: 0.2rem 0.55rem;
        border-radius: 999px;
        font-size: 0.8rem;
        background: rgba(15, 118, 110, 0.1);
        color: var(--accent);
        margin-right: 0.35rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource(show_spinner='Preparing Django data...')
def init_workspace():
    ensure_demo_ready()
    return True


def member_label(member):
    roles = [role for role, enabled in [('Owner', member.is_owner), ('HR', member.is_hr), ('Manager', member.is_manager)] if enabled]
    if not roles:
        roles = ['Employee']
    return f'{member.display_name} ({", ".join(roles)})'


def render_metric(label, value, note):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_meta_card(column, label, value):
    if isinstance(value, date):
        display_value = value.strftime('%d %b %Y')
    else:
        display_value = str(value)

    column.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-note" style="font-size: 1rem; margin-top: 0.5rem; color: var(--ink);">
                {display_value}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main():
    init_workspace()

    from todo_app.models import Organization
    from todo_app.services import can_approve_leave_request

    organizations = list(Organization.objects.order_by('name'))
    if not organizations:
        st.error('No organizations found after initialization.')
        return

    st.markdown(
        """
        <section class="hero">
            <span class="pill">Streamlit Cloud ready</span>
            <span class="pill">Django ORM powered</span>
            <h1>OfficeDiary Live Workspace</h1>
            <p>
                Existing OfficeDiary models aur demo data ko use karke yeh Streamlit workspace tasks, leave,
                people, events aur announcements ko ek live app ke roop me expose karta hai.
            </p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    org_index = st.sidebar.selectbox(
        'Organization',
        options=range(len(organizations)),
        format_func=lambda idx: organizations[idx].name,
    )
    organization = organizations[org_index]

    from todo_app.models import Membership

    org_members = list(
        Membership.objects.filter(organization=organization, active=True)
        .select_related('user', 'reporting_manager')
        .prefetch_related('teams')
        .order_by('display_name')
    )
    viewer_index = st.sidebar.selectbox(
        'View as',
        options=range(len(org_members)),
        format_func=lambda idx: member_label(org_members[idx]),
    )
    viewer = org_members[viewer_index]

    snapshot = organization_snapshot(organization.id, viewer.id)
    members = snapshot['members']
    tasks = snapshot['tasks']
    pending_leave = snapshot['pending_leave_requests']
    status_map = task_status_labels()
    stage_map = progress_stage_labels()
    blocker_map = blocker_labels()
    open_tasks = [task for task in tasks if task.status != 'done']
    overdue = overdue_tasks(tasks)
    due_soon = upcoming_task_window(tasks)
    status_counter = Counter({item['status']: item['total'] for item in snapshot['status_counts']})

    metrics = st.columns(4)
    with metrics[0]:
        render_metric('Visible Tasks', len(tasks), f'{len(open_tasks)} open for {viewer.display_name}')
    with metrics[1]:
        render_metric('Blocked', status_counter.get('blocked', 0), f'{len(overdue)} overdue items')
    with metrics[2]:
        render_metric('Pending Leave', len(pending_leave), f'{len(snapshot["events"])} upcoming events')
    with metrics[3]:
        render_metric('Members', len(members), f'{len(snapshot["announcements"])} recent announcements')

    tabs = st.tabs(['Overview', 'Tasks', 'Leave', 'People', 'Calendar'])

    with tabs[0]:
        left, right = st.columns([1.2, 1])
        with left:
            st.subheader('Status Split')
            st.bar_chart(
                {
                    'count': {
                        status_map.get(key, key): status_counter.get(key, 0)
                        for key in ['todo', 'in_progress', 'blocked', 'done']
                    }
                }
            )
            st.subheader('Due In 7 Days')
            if due_soon:
                st.dataframe(
                    [
                        {
                            'Task': task.task_key,
                            'Title': task.title,
                            'Assignee': task.primary_membership.display_name if task.primary_membership else task.primary_assignee.username,
                            'Due': task.due_date,
                            'Status': status_map.get(task.status, task.status),
                        }
                        for task in due_soon
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info('Next 7 days me koi open due task nahi hai.')
        with right:
            st.subheader('Announcements')
            if snapshot['announcements']:
                for announcement in snapshot['announcements']:
                    st.markdown(f'**{announcement.title}**')
                    st.caption(f'{announcement.publish_at:%d %b %Y, %I:%M %p} by {announcement.created_by.display_name}')
                    st.write(announcement.content)
                    st.divider()
            else:
                st.info('Abhi tak koi announcement publish nahi hua.')

    with tabs[1]:
        filter_cols = st.columns(3)
        status_filter = filter_cols[0].selectbox(
            'Status filter',
            options=['all', 'todo', 'in_progress', 'blocked', 'done'],
            format_func=lambda value: 'All statuses' if value == 'all' else status_map.get(value, value),
        )
        team_options = [('all', 'All teams')]
        team_options.extend((str(team.id), team.name) for team in organization.teams.order_by('name'))
        team_filter = filter_cols[1].selectbox('Team filter', options=range(len(team_options)), format_func=lambda idx: team_options[idx][1])
        assignee_filter = filter_cols[2].selectbox(
            'Assignee filter',
            options=['all'] + [str(member.id) for member in members],
            format_func=lambda value: 'All assignees' if value == 'all' else next(member.display_name for member in members if str(member.id) == value),
        )

        visible_tasks = tasks
        if status_filter != 'all':
            visible_tasks = [task for task in visible_tasks if task.status == status_filter]
        selected_team = team_options[team_filter][0]
        if selected_team != 'all':
            visible_tasks = [task for task in visible_tasks if task.team_id == int(selected_team)]
        if assignee_filter != 'all':
            visible_tasks = [task for task in visible_tasks if task.primary_membership_id == int(assignee_filter)]

        with st.expander('Create new task', expanded=False):
            task_team_options = [None] + list(organization.teams.order_by('name'))
            with st.form('create-task-form', clear_on_submit=True):
                title = st.text_input('Title')
                description = st.text_area('Description', height=120)
                form_cols = st.columns(3)
                assignee = form_cols[0].selectbox('Assignee', options=members, format_func=lambda member: member.display_name)
                priority = form_cols[1].selectbox('Priority', options=['Low', 'Medium', 'High'], index=1)
                task_type = form_cols[2].selectbox('Task type', options=['general', 'development'], format_func=lambda value: value.title())
                date_cols = st.columns(3)
                start_date = date_cols[0].date_input('Start date', value=None)
                due_date = date_cols[1].date_input('Due date', value=None)
                expected_next_update = date_cols[2].date_input('Expected next update', value=None)
                extra_cols = st.columns(2)
                team = extra_cols[0].selectbox(
                    'Team',
                    options=task_team_options,
                    format_func=lambda team_obj: 'No team' if team_obj is None else team_obj.name,
                )
                collaborators = extra_cols[1].multiselect(
                    'Collaborators',
                    options=[member for member in members if member.id != assignee.id],
                    format_func=lambda member: member.display_name,
                )
                if st.form_submit_button('Create task', use_container_width=True):
                    if not title.strip():
                        st.error('Title required hai.')
                    else:
                        create_task(
                            organization_id=organization.id,
                            actor_membership_id=viewer.id,
                            assignee_membership_id=assignee.id,
                            title=title.strip(),
                            description=description.strip(),
                            priority=priority,
                            task_type=task_type,
                            due_date=due_date,
                            start_date=start_date,
                            expected_next_update=expected_next_update,
                            team_id=team.id if team else None,
                            collaborator_membership_ids=[member.id for member in collaborators],
                        )
                        st.success('Task create ho gaya.')
                        st.rerun()

        if visible_tasks:
            for task in visible_tasks:
                with st.expander(f'{task.task_key} · {task.title} · {status_map.get(task.status, task.status)}', expanded=False):
                    st.write(task.description or 'No description')
                    meta_cols = st.columns(4)
                    render_meta_card(
                        meta_cols[0],
                        'Assignee',
                        task.primary_membership.display_name if task.primary_membership else task.primary_assignee.username,
                    )
                    render_meta_card(meta_cols[1], 'Priority', task.priority)
                    render_meta_card(meta_cols[2], 'Due date', task.due_date or 'Not set')
                    render_meta_card(meta_cols[3], 'Team', task.team.name if task.team else 'No team')
                    with st.form(f'update-task-{task.id}'):
                        form_cols = st.columns(3)
                        status = form_cols[0].selectbox(
                            'Status',
                            options=list(status_map.keys()),
                            index=list(status_map.keys()).index(task.status),
                            format_func=lambda value: status_map[value],
                            key=f'status-{task.id}',
                        )
                        progress_stage = form_cols[1].selectbox(
                            'Progress stage',
                            options=list(stage_map.keys()),
                            index=list(stage_map.keys()).index(task.progress_stage),
                            format_func=lambda value: stage_map[value],
                            key=f'stage-{task.id}',
                        )
                        blocked_type = form_cols[2].selectbox(
                            'Blocker',
                            options=list(blocker_map.keys()),
                            index=list(blocker_map.keys()).index(task.blocked_type),
                            format_func=lambda value: blocker_map[value],
                            key=f'blocker-{task.id}',
                        )
                        blocked_reason = st.text_area('Blocked reason', value=task.blocked_reason, key=f'blocked-reason-{task.id}')
                        reopened_reason = st.text_area('Reopened reason', value=task.reopened_reason, key=f'reopened-{task.id}')
                        comment = st.text_area('Comment / update note', key=f'comment-{task.id}')
                        if st.form_submit_button('Save task update', use_container_width=True):
                            update_task(
                                organization_id=organization.id,
                                actor_membership_id=viewer.id,
                                task_id=task.id,
                                status=status,
                                progress_stage=progress_stage,
                                blocked_type=blocked_type,
                                blocked_reason=blocked_reason,
                                reopened_reason=reopened_reason,
                                comment=comment,
                            )
                            st.success('Task update save ho gaya.')
                            st.rerun()
        else:
            st.info('Current filters me koi task visible nahi hai.')

    with tabs[2]:
        left, right = st.columns([1, 1.15])
        with left:
            st.subheader(f'Leave balance for {viewer.display_name}')
            st.dataframe(
                [
                    {
                        'Leave type': item['leave_type'].name,
                        'Allocated': item['allocated'],
                        'Available': item['available'],
                        'Used': item['used'],
                        'Pending': item['pending'],
                    }
                    for item in snapshot['leave_summary']
                ],
                use_container_width=True,
                hide_index=True,
            )
            leave_types = available_leave_types(organization.id)
            with st.form('submit-leave-form', clear_on_submit=True):
                leave_type = st.selectbox('Leave type', options=leave_types, format_func=lambda item: item.name)
                leave_cols = st.columns(2)
                start_date = leave_cols[0].date_input('From', value=None)
                end_date = leave_cols[1].date_input('To', value=None)
                reason = st.text_area('Reason')
                if st.form_submit_button('Submit leave request', use_container_width=True):
                    try:
                        submit_leave(organization.id, viewer.id, leave_type.id, start_date, end_date, reason.strip())
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.success('Leave request submit ho gayi.')
                        st.rerun()
        with right:
            st.subheader('Pending approvals')
            pending_for_viewer = [request for request in pending_leave if can_approve_leave_request(viewer, request)]
            if pending_for_viewer:
                for request in pending_for_viewer:
                    with st.expander(f'{request.membership.display_name} · {request.leave_type.name} · {request.start_date} to {request.end_date}'):
                        st.write(request.reason or 'No reason added.')
                        note = st.text_area('Approver note', key=f'leave-note-{request.id}')
                        action_cols = st.columns(2)
                        if action_cols[0].button('Approve', key=f'approve-{request.id}', use_container_width=True):
                            decide_leave(organization.id, viewer.id, request.id, True, note.strip())
                            st.success('Leave approved.')
                            st.rerun()
                        if action_cols[1].button('Reject', key=f'reject-{request.id}', use_container_width=True):
                            decide_leave(organization.id, viewer.id, request.id, False, note.strip())
                            st.warning('Leave rejected.')
                            st.rerun()
            else:
                st.info('Current viewer ke paas pending approvals nahi hain.')

    with tabs[3]:
        st.subheader('Organization members')
        st.dataframe(
            [
                {
                    'Name': member.display_name,
                    'Username': member.user.username,
                    'Roles': ', '.join(role for role, enabled in [('Owner', member.is_owner), ('HR', member.is_hr), ('Manager', member.is_manager), ('Employee', member.is_employee)] if enabled),
                    'Manager': member.reporting_manager.display_name if member.reporting_manager else '-',
                    'Teams': ', '.join(team.name for team in member.teams.all()) or '-',
                }
                for member in members
            ],
            use_container_width=True,
            hide_index=True,
        )

    with tabs[4]:
        cal_left, cal_right = st.columns(2)
        with cal_left:
            st.subheader('Upcoming holidays')
            if snapshot['holidays']:
                for holiday in snapshot['holidays']:
                    st.markdown(f'**{holiday.name}**')
                    st.caption(f'{holiday.date:%d %b %Y} · {holiday.location or "Organization wide"}')
                    if holiday.description:
                        st.write(holiday.description)
            else:
                st.info('No upcoming holidays.')
        with cal_right:
            st.subheader('Upcoming events')
            if snapshot['events']:
                for event in snapshot['events']:
                    st.markdown(f'**{event.title}**')
                    st.caption(f'{event.starts_at:%d %b %Y, %I:%M %p} · {event.location_or_link or "TBA"}')
                    st.write(event.description or 'No description')
                    st.divider()
            else:
                st.info('No upcoming events.')


if __name__ == '__main__':
    main()
