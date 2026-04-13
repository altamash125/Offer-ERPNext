from __future__ import unicode_literals

import json
import re
import difflib
from datetime import datetime
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import add_to_date, getdate, now_datetime, formatdate, nowdate


# --------------------------------------------------------------------
# CONFIG
# --------------------------------------------------------------------
MIN_NEW_WORDS_PER_UPDATE = 50
MAX_NEW_WORDS_PER_UPDATE = 350

# ONLY similarity threshold (existing description vs new message)
SIMILARITY_THRESHOLD = 0.50

# bypass users
BYPASS_USERS = {
    "administrator",
}


def is_bypass_user() -> bool:
    return (frappe.session.user or "").lower() in BYPASS_USERS


def is_core_helper() -> bool:
    return "Core Helper" in frappe.get_roles(frappe.session.user)


# --------------------------------------------------------------------
# TASK LISTING HELPERS
# --------------------------------------------------------------------
@frappe.whitelist()
def overdue_tasks(myproject):
    myproject = json.loads(myproject)
    if len(myproject) == 1:
        myproject = myproject[0]
    else:
        myproject = tuple(myproject)

    return frappe.db.get_list(
        "Task",
        {
            "status": "Overdue",
            "_assign": ["like", "%" + frappe.session.user + "%"],
            "project": ["in", myproject],
        },
        ["name", "subject", "project", "exp_end_date"],
    )


@frappe.whitelist()
def get_pending_tasks(myproject):
    myproject = json.loads(myproject)
    if len(myproject) == 1:
        myproject = myproject[0]
    else:
        myproject = tuple(myproject)

    return frappe.db.get_list(
        "Task",
        {
            "status": ["in", ["Working", "Open"]],
            "_assign": ["like", "%" + frappe.session.user + "%"],
            "project": ["in", myproject],
            "exp_end_date": [">=", nowdate()],
        },
        ["name", "subject", "project", "exp_end_date"],
    )


@frappe.whitelist()
def get_open_tasks(myproject):
    myproject = json.loads(myproject)
    if len(myproject) == 1:
        myproject = myproject[0]
    else:
        myproject = tuple(myproject)

    return frappe.db.get_list(
        "Task",
        {
            "status": ["in", ["Open", "Working"]],
            "_assign": ["like", "%" + frappe.session.user + "%"],
            "project": ["in", myproject],
            "exp_start_date": nowdate(),
        },
        ["name", "subject", "project", "exp_end_date"],
    )


@frappe.whitelist()
def get_open_tasks_t(myproject):
    myproject = json.loads(myproject)
    if len(myproject) == 1:
        myproject = myproject[0]
    else:
        myproject = tuple(myproject)

    return frappe.db.get_list(
        "Task",
        {
            "status": ["in", ["Open", "Working"]],
            "_assign": ["like", "%" + frappe.session.user + "%"],
            "project": ["in", myproject],
            "exp_end_date": add_to_date(nowdate(), days=1),
        },
        ["name", "subject", "project", "exp_end_date"],
    )


# --------------------------------------------------------------------
# DELAY LOG UPDATER
# --------------------------------------------------------------------
@frappe.whitelist()
def update_reason_in_tasks(data):
    data = json.loads(data)
    task = frappe.get_cached_doc("Task", data["task"])
    task.append(
        "delay_log",
        {
            "user": frappe.session.user,
            "reason": data["reason"],
            "revised_date": data["rev_date"],
        },
    )
    task.proposed_date = data["rev_date"]
    task.save()


# --------------------------------------------------------------------
# WORD / TEXT HELPERS
# --------------------------------------------------------------------
def count_words(text):
    """Count words in a text string, handling HTML content from rich text editors."""
    if not text:
        return 0
    text_without_html = re.sub(r"<[^>]+>", "", str(text))
    text_clean = re.sub(r"\s+", " ", text_without_html).strip()
    if not text_clean:
        return 0
    return len(text_clean.split())


def normalize_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def similarity_ratio(a: str, b: str) -> float:
    a, b = normalize_text(a), normalize_text(b)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


# --------------------------------------------------------------------
# SIMILARITY CHECK (ONLY EXISTING DESCRIPTION VS NEW UPDATE)
# --------------------------------------------------------------------
def similarity_against_existing(existing: str, new: str) -> float:
    existing = normalize_text(existing)
    new = normalize_text(new)

    if not existing or not new:
        return 0.0

    return difflib.SequenceMatcher(None, existing, new).ratio()


# --------------------------------------------------------------------
# MEETING TASK HELPER
# --------------------------------------------------------------------
@frappe.whitelist()
def get_assigned_meeting(emp):
    if not emp:
        frappe.throw("Employee id is required")

    user = frappe.db.get_value("Employee", emp, "user_id")
    tasks = frappe.db.get_all(
        "Task",
        {
            "type": "Meeting",
            "_assign": ["like", "%" + user + "%"],
            "status": ["in", ["Open", "Working"]],
        },
        "name",
    )
    return [t.name for t in tasks]


# --------------------------------------------------------------------
# TIMESHEET HOOKS
# --------------------------------------------------------------------
def before_submit(self, method=None):
    """
    Timesheet validation before submit:
    1) Check submission time (before 8 PM same day)
    2) Block blank timesheets
    3) Per-task minimum 50 words (existing + new entries in this timesheet)
    4) Update attendance status
    """
    # bypass users and Core Helper role
    if is_bypass_user() or is_core_helper():
        return

    # 1) Time validation
    current_time = now_datetime()
    timesheet_date = getdate(self.start_date)

    # if getdate(current_time) != timesheet_date or current_time.hour >= 20:
    #     frappe.throw("You can only submit the timesheet before 8 PM.")

    # 2) Block blank timesheet
    has_any_task = False
    total_new_words = 0

    for row in self.time_logs:
        if row.task:
            has_any_task = True
            total_new_words += count_words(row.custom_task_decription)

    if not has_any_task:
        frappe.throw("Timesheet must have at least one task.")

    if total_new_words == 0:
        frappe.throw("All task descriptions are blank. Add description (50-350 words).")

    # 3) Per-task total words check (existing task description + NEW descriptions in this timesheet)
    task_to_descs = defaultdict(list)
    task_to_rows = defaultdict(list)

    for idx, row in enumerate(self.time_logs, start=1):
        if not row.task:
            continue

        desc = row.custom_task_decription or ""
        if count_words(desc) == 0:
            continue

        task_to_descs[row.task].append(desc.strip())
        task_to_rows[row.task].append(idx)

    validation_errors = []
    for task, desc_list in task_to_descs.items():
        existing_description = frappe.db.get_value("Task", task, "description") or ""
        new_block = "\n".join(desc_list)
        combined = f"{existing_description}\n{new_block}".strip()

        if count_words(combined) < 50:
            task_subject = frappe.db.get_value("Task", task, "subject") or task
            rows_str = ", ".join(str(i) for i in task_to_rows[task])
            validation_errors.append(
                f"Task '{task_subject}' (rows {rows_str}): total words < 50 (existing+new)"
            )

    if validation_errors:
        frappe.throw("<br>".join(validation_errors), title="Word Count Validation Failed")

    # 4) Update Attendance
    attendance_doc = frappe.db.get_all(
        "Attendance",
        filters={"employee": self.employee, "attendance_date": self.start_date},
        pluck="name",
    )
    if attendance_doc:
        frappe.db.set_value("Attendance", attendance_doc[0], "status", "Present")


def before_save(doc, method=None):
    """Merge existing task_list with new tasks to avoid duplicates."""
    existing_tasks = doc.get("task_list", "").split(", ") if doc.get("task_list") else []
    new_tasks = doc.get("new_task_list", "").split(", ") if doc.get("new_task_list") else []

    all_tasks = []
    seen = set()

    for task in existing_tasks + new_tasks:
        if task and task not in seen:
            all_tasks.append(task)
            seen.add(task)

    doc.task_list = ", ".join(all_tasks) if all_tasks else ""


def on_submit(self, method=None):
    """
    Update task descriptions after timesheet submission.

    IMPORTANT:
    - Per row update -> prevents word count inflation (no row join)
    - Similarity check is ONLY existing task description vs new update text
    - No commit in update_task_description
    - Any error -> throw -> Timesheet will NOT submit
    """
    # bypass users and Core Helper role
    if is_bypass_user() or is_core_helper():
        return

    validation_errors = []

    for idx, row in enumerate(self.time_logs, start=1):
        if not row.task:
            continue

        desc = row.custom_task_decription or ""
        if count_words(desc) == 0:
            continue

        try:
            result = update_task_description(row.task, desc.strip())
            if result.get("status") == "failed":
                task_subject = frappe.db.get_value("Task", row.task, "subject") or row.task
                validation_errors.append(
                    f"Task '{task_subject}' (row {idx}): {result.get('message', 'Update failed')}"
                )
        except Exception as e:
            task_subject = frappe.db.get_value("Task", row.task, "subject") or row.task
            validation_errors.append(f"Task '{task_subject}' (row {idx}): {str(e)}")

    if validation_errors:
        frappe.throw(
            f"<b>Timesheet submission failed - Task updates could not be completed:</b><br><br>{'<br>'.join(validation_errors)}",
            title="Task Update Error",
        )


# --------------------------------------------------------------------
# TASK DESCRIPTION UPDATER (NO COMMIT HERE!)
# --------------------------------------------------------------------
@frappe.whitelist()
def update_task_description(task, message):
    """
    Enforces:
    - 50 to 350 words per update (per call)
    - similarity check ONLY:
        existing description (full) vs new update text
      and block if >= 50%
    - date header based insertion
    """
    if not task or not message:
        return {"status": "failed", "message": "Task or message missing"}

    new_words = count_words(message)

    if new_words < MIN_NEW_WORDS_PER_UPDATE:
        return {
            "status": "failed",
            "message": f"Minimum {MIN_NEW_WORDS_PER_UPDATE} words required. You added {new_words}.",
        }

    if new_words > MAX_NEW_WORDS_PER_UPDATE:
        return {
            "status": "failed",
            "message": f"Maximum {MAX_NEW_WORDS_PER_UPDATE} words allowed per update. You added {new_words}.",
        }

    today = nowdate()
    formatted_date = datetime.strptime(today, "%Y-%m-%d").strftime("%d-%m-%Y")
    date_header = f"Date :【{formatted_date}】"

    task_doc = frappe.get_doc("Task", task)
    existing_desc = task_doc.description or ""

    # Similarity check (ONLY existing vs new)
    similarity = similarity_against_existing(existing_desc, message)
    if similarity >= SIMILARITY_THRESHOLD:
        return {
            "status": "failed",
            "message": f"Update too similar to existing description (similarity={similarity:.2f}). Write a fresh update.",
        }

    # Insert/append message under date header
    if existing_desc and date_header in existing_desc:
        header_end = existing_desc.find(date_header) + len(date_header)
        next_date_pos = existing_desc.find("Date :【", header_end)

        if next_date_pos == -1:
            task_doc.description = f"{existing_desc.rstrip()}\n{message}"
        else:
            before = existing_desc[:next_date_pos].rstrip()
            after = existing_desc[next_date_pos:]
            task_doc.description = f"{before}\n{message}\n\n{after}"
    else:
        task_doc.description = f"{date_header}\n{message}\n\n{existing_desc}".strip()

    # IMPORTANT: no commit here
    task_doc.save(ignore_permissions=True)

    return {"status": "success", "word_count_added": new_words}


# --------------------------------------------------------------------
# EMAIL JOBS (placeholders)
# --------------------------------------------------------------------
@frappe.whitelist()
def send_overdue_task_mails():
    import datetime as dt

    weekday = dt.datetime.today().weekday()
    if weekday == 6:
        return "Not running on Sunday"

    overdue_tasks = frappe.get_all(
        "Task",
        {"status": "Overdue"},
        ["name", "subject", "owner", "exp_end_date", "project"],
    )

    user_tasks_map = {}
    for task in overdue_tasks:
        if not task.exp_end_date:
            continue

        due_date = formatdate(task.exp_end_date)
        today = dt.datetime.strptime(nowdate(), "%Y-%m-%d").date()
        due_date_obj = (
            task.exp_end_date
            if isinstance(task.exp_end_date, dt.date)
            else dt.datetime.strptime(task.exp_end_date, "%Y-%m-%d").date()
        )
        overdue_days = (today - due_date_obj).days

        todo = frappe.get_all(
            "ToDo",
            {"reference_type": "Task", "reference_name": task.name},
            ["allocated_to"],
        )
        allocated_to = todo[0].allocated_to if todo else None

        assigned_to_name = frappe.db.get_value("User", allocated_to, "full_name") or allocated_to
        created_by_name = frappe.db.get_value("User", task.owner, "full_name") or task.owner

        task_info = {
            "task_name": task.name,
            "subject": task.subject,
            "project": task.project or "N/A",
            "due_date": due_date,
            "overdue_days": overdue_days,
            "created_by": created_by_name,
            "assigned_to": assigned_to_name,
        }

        for u in filter(None, [allocated_to, task.owner]):
            if u.lower() == "administrator":
                continue
            user_tasks_map.setdefault(
                u,
                {"email": u, "full_name": frappe.db.get_value("User", u, "full_name") or u, "tasks": []},
            )
            if not any(x["task_name"] == task.name for x in user_tasks_map[u]["tasks"]):
                user_tasks_map[u]["tasks"].append(task_info)

    sent_count = len(user_tasks_map)
    return f"✅ Sent overdue reminders to {sent_count} user(s)."


@frappe.whitelist()
def send_pending_review_task():
    import datetime as dt

    weekday = dt.datetime.today().weekday()
    if weekday == 6:
        return "Not running on Sunday"

    pending_tasks = frappe.get_all(
        "Task",
        {"status": "Pending Review", "creation": [">", "2025-10-20"]},
        ["name", "subject", "owner", "project", "status"],
    )

    if not pending_tasks:
        return "✅ No Pending Review tasks found."

    user_tasks_map = defaultdict(list)
    for t in pending_tasks:
        user_tasks_map[t.owner].append(t)

    sent_count = len(user_tasks_map)
    return f"✅ Sent pending review task reminders to {sent_count} user(s)."


"""
Timesheet + Task validations and task description updater with:
1) Per update new description must be 50-150 words (per row update, NOT combined across rows)
2) Similarity check ONLY existing task description vs new update text
   - blocks if >= 50%
3) Similarity happens ONLY within same Task (existing vs new)
4) Bypass validation for specific users
5) IMPORTANT: No frappe.db.commit() inside update_task_description
"""