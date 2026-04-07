import frappe
# from frappe.utils import now_datetime,add_to_date,today
from frappe.utils import now_datetime, get_datetime, convert_utc_to_system_timezone
from datetime import timedelta


@frappe.whitelist()
def get_unread_notifications():
    """Fetch unread notifications for the logged-in user."""
    user = frappe.session.user

    # Get unread notifications for the current user
    notifications = frappe.get_all('Notification Log',
                                   filters={'read': 0, 'for_user': user},
                                   fields=['name', 'subject', 'email_content', 'document_type', 'document_name', 'creation'])

    return notifications

@frappe.whitelist()
def mark_notification_as_read(notification_name):
    """Mark the notification as read."""
    frappe.db.set_value('Notification Log', notification_name, 'read', 1)
    frappe.db.commit()
    return {'status': 'success', 'notification_name': notification_name}



# @frappe.whitelist()
# def trigger_checkout_notifications():
#     notify_checkout_for_all_employees()
#     return "✅ Notification trigger executed successfully"

# def notify_checkout_for_all_employees():
#     today = now_datetime().date()
#     start = f"{today} 00:00:00"
#     end = f"{today} 23:59:59"

#     employees = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name")

#     for emp_id in employees:
#         notify_checkout_for_employee(emp_id)

# def notify_checkout_for_employee(emp_id):
#     today = now_datetime().date()
#     start = f"{today} 00:00:00"
#     end = f"{today} 23:59:59"

#     emp = frappe.get_doc("Employee", emp_id)

#     checkin_in = frappe.get_all("Employee Checkin", 
#         filters={
#             "employee": emp.name,
#             "log_type": "IN",
#             "time": ["between", [start, end]]
#         },
#         fields=["name"],
#         limit=1
#     )

#     checkin_out = frappe.get_all("Employee Checkin", 
#         filters={
#             "employee": emp.name,
#             "log_type": "OUT",
#             "time": ["between", [start, end]]
#         },
#         fields=["name"],
#         limit=1
#     )

#     if checkin_in and not checkin_out:
#         device_id = frappe.get_value("User Device", {"user": emp.user_id}, "device_id")
#         if not device_id:
#             frappe.logger().info(f"No device_id found for {emp.name}")
#             return

#         doc = frappe.get_doc({
#             "doctype": "Firebase Notification",
#             "notification_type": "ID",
#             "title": "⏰ Check-out Reminder",
#             "body": f"Hi {emp.employee_name}, you forgot to check out today. Please do it now.",
#             "idtopic": device_id,
#             "user": emp.user_id,
#             "click_action": "/app/employee-checkin"
#         })

#         doc.insert(ignore_permissions=True)
#         doc.submit()
#         frappe.db.commit()
#         frappe.logger().info(f"Notification sent to {emp.name}")

# @frappe.whitelist()
# def trigger_checkout_notifications():
#     notify_checkout_for_all_employees()
#     return "✅ Notification triggered"


# def notify_unsubmitted_timesheet_via_firebase():
#     try:
#         today = now_datetime().date()
#         frappe.log_error("Started notify_unsubmitted_timesheet_via_firebase", str(today))

#         # Step 1: Get all active employees
#         employees = frappe.get_all(
#             "Employee",
#             filters={"status": "Active"},
#             fields=["name", "employee_name", "user_id"]
#         )

#         if not employees:
#             frappe.log_error("No active employees found", "Step 1")
#             return

#         for emp in employees:
#             try:
#                 frappe.log_error("Checking timesheet for", emp.name)

#                 # Step 2: Check for today's Timesheet that is not submitted
#                 timesheet = frappe.get_all(
#                     "Timesheet",
#                     filters={
#                         "employee": emp.name,
#                         "docstatus": 0,  # Draft only
#                         "start_date": today  # Optional: you can also check via time logs
#                     },
#                     fields=["name"],
#                     limit=1
#                 )

#                 if not timesheet:
#                     frappe.log_error(f"No draft timesheet found for {emp.name}", "Skipping")
#                     continue

#                 # Step 3: Get device ID for push notification
#                 device_id = frappe.get_value("User Device", {"user": emp.user_id}, "device_id")
#                 if not device_id:
#                     frappe.log_error(f"No device ID found for {emp.user_id}", f"Step 3: {emp.name}")
#                     continue

#                 frappe.log_error(f"Creating Firebase Notification for {emp.employee_name}", f"Step 4 Device: {device_id}")

#                 # Step 4: Send Firebase Notification
#                 doc = frappe.get_doc({
#                     "doctype": "Firebase Notification",
#                     "notification_type": "ID",
#                     "title": "📝 Timesheet Reminder",
#                     "body": f"Hi {emp.employee_name}, your timesheet for today is pending. Please submit it.",
#                     "idtopic": device_id,
#                     "user": emp.user_id,
#                     "server_response": "/app/timesheet"
#                 })

#                 doc.insert(ignore_permissions=True)
#                 doc.submit()
#                 frappe.db.commit()

#                 frappe.log_error(f"Notification created for {emp.name}", f"Notification Doc: {doc.name}")

#             except Exception as e:
#                 frappe.log_error(f"Error for employee {emp.name}", str(e))

#     except Exception as main_err:
#         frappe.log_error("notify_unsubmitted_timesheet_via_firebase Failed", str(main_err))



# # def send_offline_meeting_reminders():
# #     now = now_datetime()
# #     current_date = today()  # 'YYYY-MM-DD'
# #     frappe.log_error("now time",now)
# #     events = frappe.get_all(
# #         "Event",
# #         filters={
# #             "event_category": "Meeting",
# #             "event_meeting_mode": "Offline",
# #             "creation": ["like", f"{current_date}%"],  # Creation date starts with today's date
# #         },
# #         fields=["name", "subject", "owner", "starts_on","creation"]
# #     )
# #     frappe.log_error("evnets",events)
# #     for event in events:
# #         diff_minutes = (event.starts_on - now).total_seconds() / 60
# #         frappe.log_error("diff",diff_minutes)
# #         # 🔥 Exactly 5 minutes left (with buffer)
# #         if 4 <= diff_minutes <= 6:
# #             send_firebase_notification(event)


# def send_offline_meeting_reminders():
#     now = now_datetime()
    
#     events = frappe.get_all(
#         "Event",
#         filters=[
#             ["event_category", "=", "Meeting"],
#             ["event_meeting_mode", "=", "Offline"],
#             ["starts_on", ">=", now - timedelta(minutes=5)],
#             ["starts_on", "<=", now + timedelta(minutes=5)]
#         ],
#         fields=["name", "subject", "owner", "starts_on"],
#         limit_page_length=10,
#         order_by="starts_on asc"
#     )
    
#     print(f"Found {len(events)} imminent events at {now}")
    
#     for event in events:
#         event_time = get_datetime(event.starts_on)
#         diff_minutes = (event_time - now).total_seconds() / 60
        
#         print(f"  {event.name}: {event.subject[:30]}... → {diff_minutes:.1f} min")
        
#         if 0 <= diff_minutes <= 5:
#             print(f"    ✅ Sending notification for {event.name}")
#             send_firebase_notification(event)
#         else:
#             print(f"    ⏳ Waiting: {diff_minutes:.1f} min")


# def send_firebase_notification(event):
#     device_id = frappe.get_value(
#         "User Device",
#         {"user": event.owner},
#         "device_id"
#     )

#     if not device_id:
#         return

#     doc = frappe.get_doc({
#         "doctype": "Firebase Notification",
#         "notification_type": "ID",
#         "title": "📍 Offline Meeting Reminder",
#         "body": f"Your meeting '{event.subject}' will start in 5 minutes.",
#         "idtopic": device_id,
#         "user": event.owner,
#         "click_action": f"/app/event/{event.name}"
#     })

#     doc.insert(ignore_permissions=True)
#     doc.submit()
