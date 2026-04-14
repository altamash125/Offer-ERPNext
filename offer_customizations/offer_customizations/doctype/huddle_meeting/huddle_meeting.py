import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, nowdate, getdate
from frappe.desk.form.assign_to import add as assign_task
import re

class HuddleMeeting(Document):
	def validate(self):
		self.check_allowed_project()
        
		for row in self.tasks_to_discuss:
			if not row.expected_time_in_hours > 0:
				frappe.throw(f"Enter expected time in Discussed Tasks Row: #{row.idx}")
		for row in self.task_to_be_created:
			if not row.expected_hours > 0:
				frappe.throw(f"Enter expected time in New Tasks Row: #{row.idx}")
		self.mark_complete()
		"""
		Check tasks in `tasks_to_discuss` child table.
		- If `task_name` is blank, create a new Task and update the field.
		- If `task_name` exists, skip it.
    	"""
		
	def check_allowed_project(self):
		for row in self.tasks_to_discuss:
			if not frappe.db.get_value('Project User',{'parent':row.project,'user': row.user},'name'):
				frappe.throw(f'Row #{row.idx}: User <b>{row.user}</b> is not a part of <b>{row.project}</b>')
		for row in self.task_to_be_created:
			if not frappe.db.get_value('Project User',{'parent':row.project,'user': row.assign_to},'name'):
				frappe.throw(f'Row #{row.idx}: User <b>{row.assign_to}</b> is not a part of <b>{row.project}</b>')
    
    

	

	@frappe.whitelist()
	def get_tasks(self):
		# Build filters
  
        # Build filters without _assign filter
		filters = {
			"status": ["not in", ["Completed", "Cancelled"]]
		}

		tasks = frappe.db.get_list(
			"Task",
			filters=filters,
			fields=[
				"project",
				"subject",
				"name",
				"type",
				"status",
				"exp_start_date",
				"exp_end_date",
				"expected_time",
				"_assign",
				"progress"
			],
			limit=1000  # Optional: Increase fetch limit
		)


		# ✅ Get existing task-user pairs
		existing_task_user_pairs = {(d.task, d.user) for d in self.get('tasks_to_discuss', [])}

		# ✅ Find new tasks (excluding those already added for the same user)
		new_tasks = []
		for task in tasks:
			assigned_users = []
			if task._assign:
				try:
					assigned_users = frappe.parse_json(task._assign)  # Convert JSON string to list
				except:
					assigned_users = []

			# ✅ Check if task is assigned to the selected user
			if self.user in assigned_users and (task.name, self.user) not in existing_task_user_pairs:
				new_tasks.append(task)

		if not new_tasks:
			frappe.msgprint("No new tasks found for this user.")
			return {"tasks_added": 0}

		for task in new_tasks:
			task_type = task.type if task.type else ""

			assigned_users = []
			if task._assign:
				try:
					assigned_users = frappe.parse_json(task._assign)
				except:
					assigned_users = []

			row = {
				"user": self.user,  
				"project": task.project,
				"subject": task.subject,
				"task": task.name,
				"type": task_type,
				"status": task.status,
				"start_date": task.exp_start_date,
				"end_date": task.exp_end_date,
				"expected_time_in_hours": task.expected_time or 0,
				"assigned_to": ", ".join(assigned_users),
				"task_percentage":task.progress
			}

			if task.exp_start_date and task.exp_end_date:
				row["total_days"] = date_diff(task.exp_end_date, task.exp_start_date)

			self.append('tasks_to_discuss', row)

		frappe.msgprint(f"{len(new_tasks)} new tasks added for {self.user}.")
		return {"tasks_added": len(new_tasks)}


	def on_submit(self):
		if self.date == nowdate():
			self.user_task_map = frappe._dict()
			self.process_tasks_to_discuss()
			self.create_tasks()
			# self.mark_complete()
			self.reload()
			create_timesheet(self.name, self.user_task_map)

	def mark_complete(self):
		try:
			for row in self.tasks_to_discuss:
				if (
					row.action == "Status Update"
					and row.status == "Completed"
					and row.task
				):
					try:
						# Update Task
						frappe.db.set_value(
							"Task",
							row.task,
							{
								"status": "Completed",
								"completed_by": row.user,
								"completed_on": self.date,
								"progress": 100,
								"color": "#2020ff",
								"expected_time": row.expected_time_in_hours,
							}
						)

					except Exception:
						# Error in single task row
						frappe.log_error(
							title=f"Hurdle Meeting Task Update Error | Task: {row.task}",
							message=frappe.get_traceback(),
						)

		except Exception:
			# Error in whole document
			frappe.log_error(
				title=f"Hurdle Meeting Submit Error | {self.name}",
				message=frappe.get_traceback(),
			)



	@frappe.whitelist()
	def process_timesheets(self):
		self.user_task_map = frappe._dict()
		self.process_tasks_to_discuss()
		self.create_tasks()
		self.reload()
		create_timesheet(self.name, self.user_task_map)

	def process_tasks_to_discuss(self):
		if self.get('__unsaved'):
			frappe.throw('You have unsaved changes in your form. Kindly Save and Try Again')
		self.reload()
		for row in self.tasks_to_discuss:
			self.user_task_map.setdefault(row.user,{'tasks':[],'myproject':set()})
			
			if row.action == "Reassign":
				self.user_task_map[row.user].get('tasks',[]).append(row.task)
				self.user_task_map[row.user].get('myproject').add(row.project)
				doc = frappe.get_doc("Task", row.task)
				usr_lst = doc._assign[1:-2].replace('"', "").split(", ")
				for usr in usr_lst:
					frappe.desk.form.assign_to.remove(doc.doctype, doc.name, usr)
				frappe.db.set_value(
					"Task", doc.name, {"exp_end_date": row.reassign_end_date,"expected_time":row.expected_time_in_hours}
				)
				frappe.desk.form.assign_to.add(
					{
						"assign_to": [row.user],
						"doctype": doc.doctype,
						"name": doc.name,
					}
				)

			if row.action == 'Add For Today':
				frappe.db.set_value("Task", row.task, {'expected_time':row.expected_time_in_hours})
				self.user_task_map[row.user].get('tasks',[]).append(row.task)
				self.user_task_map[row.user].get('myproject').add(row.project)
				
			if row.action == 'Status Update':
				if row.status == 'Completed':
					frappe.db.set_value('Task',row.task,{'status':row.status,'completed_by':row.user,'completed_on':self.date,"progress":100, "color": "#2020ff",
									"expected_time":row.expected_time_in_hours})

					if row.task:
						issue_id = frappe.db.get_value("Task", row.task, "custom_issue_id")
						if issue_id:
							frappe.db.set_value("Issue", issue_id,"status","Completed",)

				else:
					frappe.db.set_value("Task", row.task, {"status": row.status,"expected_time":row.expected_time_in_hours})

		create_timesheet(hm_name = self.name,user_task_map = self.user_task_map)


	@frappe.whitelist()
	def create_tasks(self):
		if self.get('__unsaved'):
			frappe.throw('You have unsaved changes in your form. Kindly Save and Try Again')
		self.reload()

		if not hasattr(self, 'user_task_map'):
			self.user_task_map = {}  # Initialize it if not defined

		if not self.get('task_to_be_created', []):
			return

		for i in self.task_to_be_created:
			try:
				self.user_task_map.setdefault(i.assign_to, {'tasks': [], 'myproject': set()})
				
			
				if not i.task:
					p = frappe.get_doc({
						"doctype": "Task",
						"subject": i.subject,
						"project": i.project,
						"type": i.task_type,
						"description": i.description,
						"exp_start_date": i.exp_start_date,
						"exp_end_date": i.exp_end_date,
						"expected_time": i.expected_hours
					}).insert(ignore_permissions=True)

					frappe.db.set_value('New Task', i.name, 'task', p.name)
					i.reload()

				
					frappe.get_doc({
						"doctype": "ToDo",
						"description": f"Task Assignment for {p.name}",
						"reference_type": "Task",
						"reference_name": p.name,
						"allocated_to": i.assign_to,
						"status": "Open"
					}).insert(ignore_permissions=True)

					

				if i.exp_start_date == getdate(nowdate()) and i.task:
					self.user_task_map[i.assign_to]['tasks'].append(i.task)
					self.user_task_map[i.assign_to]['myproject'].add(i.project)

			except Exception as e:
				frappe.msgprint(f"Error in Row #.{i.idx} : {str(e)}")


	@frappe.whitelist()
	def update_timesheets(self):
		user_task_map = frappe._dict()
		for row in self.tasks_to_discuss:
			if row.action in ['Add For Today','Reassign']:
				user_task_map.setdefault(row.user,{'tasks':[],'myproject':set()})
				user_task_map[row.user].get('tasks',[]).append(row.task)
				user_task_map[row.user].get('myproject').add(row.project)
		
		for row in self.task_to_be_created:
			if row.task and row.exp_start_date == nowdate():
				user_task_map.setdefault(row.assign_to,{'tasks':[],'myproject':set()})
				user_task_map[row.assign_to].get('tasks',[]).append(row.task)
				user_task_map[row.assign_to].get('myproject').add(row.project)
				
		create_timesheet(self.name, user_task_map)
  


def create_timesheet(hm_name, user_task_map):
	"""
	Creates or updates a Timesheet for today.

	KEY CHANGES:
	1. time_logs rows are NOT added here — user will start timer manually.
	   Only task_list and myproject fields are updated so the timer dialog
	   knows which tasks are available.
	2. If today's timesheet is already submitted (docstatus=1), a NEW draft
	   timesheet is created for today so new tasks can be added.
	"""
	count = 0
	try:
		for user in user_task_map:
			if not user:
				continue

			employee_details = frappe.db.get_value(
				'Employee',
				{'user_id': user},
				['name', 'employee_name', 'department'],
				as_dict=1
			)

			if not employee_details:
				frappe.msgprint(f"No employee found for user {user}")
				continue

			new_tasks = user_task_map[user].get('tasks', [])
			new_projects = list(user_task_map[user].get('myproject', []))

			try:
				# ✅ FIX 2: Look for a DRAFT timesheet only (docstatus=0)
				# If submitted timesheet exists, we create a fresh draft for new tasks
				existing_draft = frappe.db.get_value(
					'Timesheet',
					{
						'employee': employee_details.name,
						'start_date': nowdate(),
						'docstatus': 0  # Only draft timesheets
					},
					'name'
				)

				if existing_draft:
					doc = frappe.get_doc('Timesheet', existing_draft)
				else:
					# Create new draft timesheet (even if submitted one exists for today)
					doc = frappe.new_doc('Timesheet')
					doc.employee = employee_details.name
					doc.employee_name = employee_details.employee_name
					doc.department = employee_details.department
					doc.start_date = nowdate()
					doc.end_date = nowdate()
					doc.hurdle_meeting = hm_name

				# ✅ Merge task_list (plain text field for timer dialog to read)
				existing_task_list = [t for t in (doc.get('task_list') or '').split(', ') if t]
				all_tasks = list(dict.fromkeys(existing_task_list + new_tasks))
				doc.task_list = ', '.join(all_tasks)

				# ✅ Merge myproject (plain text field)
				existing_projects = [p for p in (doc.get('myproject') or '').split(', ') if p]
				all_projects = list(dict.fromkeys(existing_projects + new_projects))
				doc.myproject = ', '.join(all_projects)

				# ✅ FIX 1: Do NOT add time_logs rows here.
				# Rows will be created when the user manually starts the timer.
				# This prevents auto-start behaviour.

				doc.flags.ignore_mandatory = True
				doc.save(ignore_permissions=True)
				frappe.db.commit()
				count += 1

			except Exception as e:
				frappe.log_error(
					title=f"Timesheet Error for {user}",
					message=frappe.get_traceback()
				)
				frappe.db.rollback()
				continue

	except Exception as e:
		frappe.log_error(str(e), 'Error in timesheet creation')
		frappe.db.rollback()
		raise

	finally:
		if count > 0:
			frappe.msgprint(f'{count} Timesheet(s) Created/Updated')






# import frappe
# from frappe import _
# from frappe.model.document import Document
# from frappe.utils import date_diff, nowdate, getdate
# from frappe.desk.form.assign_to import add as assign_task
# import re

# class HuddleMeeting(Document):
# 	def validate(self):
# 		self.check_allowed_project()
        
# 		for row in self.tasks_to_discuss:
# 			if not row.expected_time_in_hours > 0:
# 				frappe.throw(f"Enter expected time in Discussed Tasks Row: #{row.idx}")
# 		for row in self.task_to_be_created:
# 			if not row.expected_hours > 0:
# 				frappe.throw(f"Enter expected time in New Tasks Row: #{row.idx}")
# 		self.mark_complete()
# 		"""
# 		Check tasks in `tasks_to_discuss` child table.
# 		- If `task_name` is blank, create a new Task and update the field.
# 		- If `task_name` exists, skip it.
#     	"""
		
# 	def check_allowed_project(self):
# 		for row in self.tasks_to_discuss:
# 			if not frappe.db.get_value('Project User',{'parent':row.project,'user': row.user},'name'):
# 				frappe.throw(f'Row #{row.idx}: User <b>{row.user}</b> is not a part of <b>{row.project}</b>')
# 		for row in self.task_to_be_created:
# 			if not frappe.db.get_value('Project User',{'parent':row.project,'user': row.assign_to},'name'):
# 				frappe.throw(f'Row #{row.idx}: User <b>{row.assign_to}</b> is not a part of <b>{row.project}</b>')
    
    

	

# 	@frappe.whitelist()
# 	def get_tasks(self):
# 		# Build filters
  
#         # Build filters without _assign filter
# 		filters = {
# 			"status": ["not in", ["Completed", "Cancelled"]]
# 		}

# 		tasks = frappe.db.get_list(
# 			"Task",
# 			filters=filters,
# 			fields=[
# 				"project",
# 				"subject",
# 				"name",
# 				"type",
# 				"status",
# 				"exp_start_date",
# 				"exp_end_date",
# 				"expected_time",
# 				"_assign",
# 				"progress"
# 			],
# 			limit=1000  # Optional: Increase fetch limit
# 		)


# 		# ✅ Get existing task-user pairs
# 		existing_task_user_pairs = {(d.task, d.user) for d in self.get('tasks_to_discuss', [])}

# 		# ✅ Find new tasks (excluding those already added for the same user)
# 		new_tasks = []
# 		for task in tasks:
# 			assigned_users = []
# 			if task._assign:
# 				try:
# 					assigned_users = frappe.parse_json(task._assign)  # Convert JSON string to list
# 				except:
# 					assigned_users = []

# 			# ✅ Check if task is assigned to the selected user
# 			if self.user in assigned_users and (task.name, self.user) not in existing_task_user_pairs:
# 				new_tasks.append(task)

# 		if not new_tasks:
# 			frappe.msgprint("No new tasks found for this user.")
# 			return {"tasks_added": 0}

# 		for task in new_tasks:
# 			task_type = task.type if task.type else ""

# 			assigned_users = []
# 			if task._assign:
# 				try:
# 					assigned_users = frappe.parse_json(task._assign)
# 				except:
# 					assigned_users = []

# 			row = {
# 				"user": self.user,  
# 				"project": task.project,
# 				"subject": task.subject,
# 				"task": task.name,
# 				"type": task_type,
# 				"status": task.status,
# 				"start_date": task.exp_start_date,
# 				"end_date": task.exp_end_date,
# 				"expected_time_in_hours": task.expected_time or 0,
# 				"assigned_to": ", ".join(assigned_users),
# 				"task_percentage":task.progress
# 			}

# 			if task.exp_start_date and task.exp_end_date:
# 				row["total_days"] = date_diff(task.exp_end_date, task.exp_start_date)

# 			self.append('tasks_to_discuss', row)

# 		frappe.msgprint(f"{len(new_tasks)} new tasks added for {self.user}.")
# 		return {"tasks_added": len(new_tasks)}


# 	def on_submit(self):
# 		if self.date == nowdate():
# 			self.user_task_map = frappe._dict()
# 			self.process_tasks_to_discuss()
# 			self.create_tasks()
# 			# self.mark_complete()
# 			self.reload()
# 			create_timesheet(self.name, self.user_task_map)

# 	def mark_complete(self):
# 		try:
# 			for row in self.tasks_to_discuss:
# 				if (
# 					row.action == "Status Update"
# 					and row.status == "Completed"
# 					and row.task
# 				):
# 					try:
# 						# Update Task
# 						frappe.db.set_value(
# 							"Task",
# 							row.task,
# 							{
# 								"status": "Completed",
# 								"completed_by": row.user,
# 								"completed_on": self.date,
# 								"progress": 100,
# 								"color": "#2020ff",
# 								"expected_time": row.expected_time_in_hours,
# 							}
# 						)

# 					except Exception:
# 						# Error in single task row
# 						frappe.log_error(
# 							title=f"Hurdle Meeting Task Update Error | Task: {row.task}",
# 							message=frappe.get_traceback(),
# 						)

# 		except Exception:
# 			# Error in whole document
# 			frappe.log_error(
# 				title=f"Hurdle Meeting Submit Error | {self.name}",
# 				message=frappe.get_traceback(),
# 			)



# 	@frappe.whitelist()
# 	def process_timesheets(self):
# 		self.user_task_map = frappe._dict()
# 		self.process_tasks_to_discuss()
# 		self.create_tasks()
# 		self.reload()
# 		create_timesheet(self.name, self.user_task_map)

# 	def process_tasks_to_discuss(self):
# 		if self.get('__unsaved'):
# 			frappe.throw('You have unsaved changes in your form. Kindly Save and Try Again')
# 		self.reload()
# 		for row in self.tasks_to_discuss:
# 			self.user_task_map.setdefault(row.user,{'tasks':[],'myproject':set()})
			
# 			if row.action == "Reassign":
# 				self.user_task_map[row.user].get('tasks',[]).append(row.task)
# 				self.user_task_map[row.user].get('myproject').add(row.project)
# 				doc = frappe.get_doc("Task", row.task)
# 				usr_lst = doc._assign[1:-2].replace('"', "").split(", ")
# 				for usr in usr_lst:
# 					frappe.desk.form.assign_to.remove(doc.doctype, doc.name, usr)
# 				frappe.db.set_value(
# 					"Task", doc.name, {"exp_end_date": row.reassign_end_date,"expected_time":row.expected_time_in_hours}
# 				)
# 				frappe.desk.form.assign_to.add(
# 					{
# 						"assign_to": [row.user],
# 						"doctype": doc.doctype,
# 						"name": doc.name,
# 					}
# 				)

# 			if row.action == 'Add For Today':
# 				frappe.db.set_value("Task", row.task, {'expected_time':row.expected_time_in_hours})
# 				self.user_task_map[row.user].get('tasks',[]).append(row.task)
# 				self.user_task_map[row.user].get('myproject').add(row.project)
				
# 			if row.action == 'Status Update':
# 				if row.status == 'Completed':
# 					frappe.db.set_value('Task',row.task,{'status':row.status,'completed_by':row.user,'completed_on':self.date,"progress":100, "color": "#2020ff",
# 									"expected_time":row.expected_time_in_hours})

# 					if row.task:
# 						issue_id = frappe.db.get_value("Task", row.task, "custom_issue_id")
# 						if issue_id:
# 							frappe.db.set_value("Issue", issue_id,"status","Completed",)

# 				else:
# 					frappe.db.set_value("Task", row.task, {"status": row.status,"expected_time":row.expected_time_in_hours})

# 		create_timesheet(hm_name = self.name,user_task_map = self.user_task_map)


# 	@frappe.whitelist()
# 	def create_tasks(self):
# 		if self.get('__unsaved'):
# 			frappe.throw('You have unsaved changes in your form. Kindly Save and Try Again')
# 		self.reload()

# 		if not hasattr(self, 'user_task_map'):
# 			self.user_task_map = {}  # Initialize it if not defined

# 		if not self.get('task_to_be_created', []):
# 			return

# 		for i in self.task_to_be_created:
# 			try:
# 				self.user_task_map.setdefault(i.assign_to, {'tasks': [], 'myproject': set()})
				
			
# 				if not i.task:
# 					p = frappe.get_doc({
# 						"doctype": "Task",
# 						"subject": i.subject,
# 						"project": i.project,
# 						"type": i.task_type,
# 						"description": i.description,
# 						"exp_start_date": i.exp_start_date,
# 						"exp_end_date": i.exp_end_date,
# 						"expected_time": i.expected_hours
# 					}).insert(ignore_permissions=True)

# 					frappe.db.set_value('New Task', i.name, 'task', p.name)
# 					i.reload()

				
# 					frappe.get_doc({
# 						"doctype": "ToDo",
# 						"description": f"Task Assignment for {p.name}",
# 						"reference_type": "Task",
# 						"reference_name": p.name,
# 						"allocated_to": i.assign_to,
# 						"status": "Open"
# 					}).insert(ignore_permissions=True)

					

# 				if i.exp_start_date == getdate(nowdate()) and i.task:
# 					self.user_task_map[i.assign_to]['tasks'].append(i.task)
# 					self.user_task_map[i.assign_to]['myproject'].add(i.project)

# 			except Exception as e:
# 				frappe.msgprint(f"Error in Row #.{i.idx} : {str(e)}")


# 	@frappe.whitelist()
# 	def update_timesheets(self):
# 		user_task_map = frappe._dict()
# 		for row in self.tasks_to_discuss:
# 			if row.action in ['Add For Today','Reassign']:
# 				user_task_map.setdefault(row.user,{'tasks':[],'myproject':set()})
# 				user_task_map[row.user].get('tasks',[]).append(row.task)
# 				user_task_map[row.user].get('myproject').add(row.project)
		
# 		for row in self.task_to_be_created:
# 			if row.task and row.exp_start_date == nowdate():
# 				user_task_map.setdefault(row.assign_to,{'tasks':[],'myproject':set()})
# 				user_task_map[row.assign_to].get('tasks',[]).append(row.task)
# 				user_task_map[row.assign_to].get('myproject').add(row.project)
				
# 		create_timesheet(self.name, user_task_map)
  


# def create_timesheet(hm_name, user_task_map):
#     count = 0
#     try:
#         for user in user_task_map:
#             if not user:
#                 continue

#             employee_details = frappe.db.get_value(
#                 'Employee',
#                 {'user_id': user},
#                 ['name', 'employee_name', 'department'],
#                 as_dict=1
#             )

#             if not employee_details:
#                 frappe.msgprint(f"No employee found for user {user}")
#                 continue

#             # Check for existing draft timesheet for today
#             existing = frappe.db.get_value(
#                 'Timesheet',
#                 {
#                     'employee': employee_details.name,
#                     'start_date': nowdate(),
#                     'docstatus': ['<', 2]
#                 },
#                 'name'
#             )

#             try:
#                 if existing:
#                     doc = frappe.get_doc('Timesheet', existing)
#                     if doc.docstatus == 1:
#                         frappe.msgprint(f"Timesheet {doc.name} already submitted for {user}")
#                         continue
#                 else:
#                     doc = frappe.new_doc('Timesheet')
#                     doc.employee = employee_details.name
#                     doc.employee_name = employee_details.employee_name
#                     doc.department = employee_details.department
#                     doc.start_date = nowdate()
#                     doc.end_date = nowdate()
#                     doc.hurdle_meeting = hm_name

#                 # ✅ Merge plain text fields (your custom fields)
#                 existing_projects = [p for p in (doc.get('myproject') or '').split(', ') if p]
#                 new_projects = user_task_map[user].get('myproject', [])
#                 all_projects = list(dict.fromkeys(existing_projects + list(new_projects)))
#                 doc.myproject = ', '.join(all_projects)

#                 existing_task_list = [t for t in (doc.get('task_list') or '').split(', ') if t]
#                 new_tasks = user_task_map[user].get('tasks', [])
#                 all_tasks = list(dict.fromkeys(existing_task_list + list(new_tasks)))
#                 doc.task_list = ', '.join(all_tasks)

#                 # ✅ Add time_logs rows for each task (so timesheet is visible & usable)
#                 existing_time_log_tasks = {
#                     row.task for row in doc.get('time_logs', []) if row.task
#                 }

#                 for task_name in new_tasks:
#                     if not task_name:
#                         continue

#                     # Skip if this task already has a time_log row
#                     if task_name in existing_time_log_tasks:
#                         continue

#                     # Fetch task details
#                     task_doc = frappe.db.get_value(
#                         'Task',
#                         task_name,
#                         ['subject', 'project', 'expected_time', 'description'],
#                         as_dict=1
#                     )
#                     if not task_doc:
#                         continue

#                     expected_hours = task_doc.expected_time or 1.0

#                     doc.append('time_logs', {
#                         'task': task_name,
#                         'project': task_doc.project,
#                         'subject': task_doc.subject,
#                         'employee': employee_details.name,
#                         'hours': expected_hours,
#                         'expected_hours': expected_hours,
#                         'from_time': frappe.utils.now_datetime().replace(hour=9, minute=0, second=0),
#                         'to_time': frappe.utils.now_datetime().replace(hour=9, minute=0, second=0) + frappe.utils.datetime.timedelta(hours=expected_hours),
#                         'completed': 0,
#                     })

#                 doc.flags.ignore_mandatory = True
#                 doc.save(ignore_permissions=True)
#                 frappe.db.commit()
#                 count += 1

#             except Exception as e:
#                 frappe.log_error(
#                     title=f"Timesheet Error for {user}",
#                     message=frappe.get_traceback()
#                 )
#                 frappe.db.rollback()
#                 continue

#     except Exception as e:
#         frappe.log_error(str(e), 'Error in timesheet creation')
#         frappe.db.rollback()
#         raise

#     finally:
#         if count > 0:
#             frappe.msgprint(f'{count} Timesheet(s) Created')


# def create_timesheet(hm_name, user_task_map):
# 	try:
# 		count = 0
# 		for user in user_task_map:
# 			if not user:
# 				continue

# 			# Get employee details
# 			employee_details = frappe.db.get_value(
# 				'Employee',
# 				{'user_id': user},
# 				['name', 'employee_name', 'department'],
# 				as_dict=1
# 			)

# 			if not employee_details:
# 				frappe.msgprint(f"No employee found for user {user}")
# 				continue

# 			# Check for existing timesheet
# 			existing = frappe.db.get_value(
# 				'Timesheet',
# 				{
# 					'employee': employee_details.name,
# 					'start_date': nowdate(),
# 					'docstatus': ['<', 2]
# 				},
# 				'name'
# 			)

# 			try:
# 				if existing:
# 					doc = frappe.get_doc('Timesheet', existing)
# 					if doc.docstatus == 1:
# 						frappe.msgprint(f"Timesheet {doc.name} is already submitted for {user}")
# 						continue
# 				else:
# 					doc = frappe.new_doc('Timesheet')
# 					doc.employee = employee_details.name
# 					doc.employee_name = employee_details.employee_name
# 					doc.department = employee_details.department
# 					doc.start_date = nowdate()
# 					doc.hurdle_meeting = hm_name

# 				# ✅ Extract & merge projects properly
# 				existing_projects = doc.myproject.split(', ') if doc.myproject else []
# 				new_projects = list(user_task_map[user].get('myproject', []))  # Ensure it's a list

# 				all_projects = []
# 				seen_projects = set()
# 				for project in existing_projects + new_projects:
# 					if project and project not in seen_projects:
# 						all_projects.append(project)
# 						seen_projects.add(project)

# 				doc.myproject = ', '.join(all_projects) if all_projects else ''

# 				# ✅ Extract & merge tasks properly
# 				existing_tasks = doc.task_list.split(', ') if doc.task_list else []
# 				new_tasks = user_task_map[user].get('tasks', [])

# 				all_tasks = []
# 				seen_tasks = set()
# 				for task in existing_tasks + new_tasks:
# 					if task and task not in seen_tasks:
# 						all_tasks.append(task)
# 						seen_tasks.add(task)

# 				doc.task_list = ', '.join(all_tasks) if all_tasks else ''

# 				# ✅ Save the timesheet
# 				doc.flags.ignore_mandatory = True
# 				doc.save(ignore_permissions=True)
# 				count += 1
# 				frappe.db.commit()  # Commit after each successful save

# 			except Exception as e:
# 				frappe.log_error(f"Error processing timesheet for user {user}: {str(e)}")
# 				frappe.db.rollback()
# 				continue

# 		return count

# 	except Exception as e:
# 		frappe.log_error(str(e), 'Error in timesheet creation')
# 		frappe.db.rollback()
# 		raise

# 	finally:
# 		if count > 0:
# 			frappe.msgprint(f'{count} Timesheet(s) Created/Updated')





