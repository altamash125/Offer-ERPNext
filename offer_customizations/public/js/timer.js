frappe.provide("offer_customizations.custmizations.timesheet");

offer_customizations.custmizations.timesheet.timer = function (frm, row, timestamp = 0) {
    let dialog = new frappe.ui.Dialog({
        title: __("Timer"),
        fields:
            [
                {
                    "fieldtype": "Link", "label": __("Activity Type"), "fieldname": "activity_type",
                    "reqd": 1, "options": "Activity Type"
                },

                {
                    "fieldtype": "Data", "label": __("Task List"), "fieldname": 'task_list', "hidden": 1,
                },
                {
                    "fieldtype": "Link", "label": __("Task"), "fieldname": "task", "options": "Task",
                    "reqd": 1,
                    get_query: function () {

                        // const task_list = dialog.fields_dict.task_list.value; // Fetch the value
                        let task_list = frm.doc.task_list
                        console.log("Task List: ", task_list);
                        console.log("Type of Task List: ", typeof task_list);

                        let filters = {};
                        if (typeof task_list === 'string' && task_list.trim() !== '') {
                            // Split the string into an array of task IDs
                            let task_ids = task_list.split(',').map(task_id => task_id.trim());
                            console.log(task_ids)
                            filters['name'] = ['in', task_ids];
                        }

                        // filters = { 'name': ['in', dialog.fields_dict.task_list.value] }
                        if (dialog.fields_dict.project.value) {
                            filters['project'] = dialog.fields_dict.project.value
                        }
                        console.log("Filters applied: ", filters);

                        return { filters: filters };

                    },
                    onchange: function () {
                        if (dialog.fields_dict.task.value) {
                            frappe.db.get_value('Task', dialog.fields_dict.task.value, ['project', 'expected_time'], (r) => {
                                dialog.set_values({ 'project': r.project, 'expected_hours': r.expected_time })
                            })
                        }
                    }
                },
                {
                    "fieldtype": "Link", "label": __("Project"), "fieldname": "project", "options": "Project",
                    "reqd": 1,
                    get_query: function () {
                        var p_list = []
                        for (var i = 0; i < frm.doc.projects.length; i++) { p_list.push(frm.doc.projects[i].project) }
                        return {
                            filters: { 'name': ['in', p_list] }
                        }
                    }
                },
                { "fieldtype": "Float", "label": __("Expected Hrs"), "fieldname": "expected_hours", "read_only": 1 },
                { "fieldtype": "Float", "label": __("Progress Percentage"), "fieldname": "progress_percentage", "fetch_from": "task.progress", "fetch_if_empty": 1 },
                { "fieldtype": "Section Break" },
                { "fieldtype": "HTML", "fieldname": "timer_html" }
            ]
    });

    if (row) {
        dialog.set_values({
            'activity_type': row.activity_type,
            'project': row.project,
            'task': row.task,
            'expected_hours': row.expected_hours,
            'progress': row.progress_percentage
        });
    }
    dialog.get_field("timer_html").$wrapper.append(get_timer_html());
    function get_timer_html() {
        return `
			<div class="stopwatch">
				<span class="hours">00</span>
				<span class="colon">:</span>
				<span class="minutes">00</span>
				<span class="colon">:</span>
				<span class="seconds">00</span>
			</div>
			<div class="playpause text-center">
				<button class= "btn btn-primary btn-start"> ${__("Start")} </button>
				<button class= "btn btn-primary btn-stop"> ${__("Stop")} </button>
				<button class= "btn btn-primary btn-complete"> ${__("Complete")} </button>
			</div>
		`;
    }
    let t_list = [];
    if (frm.doc.task_list) {
        t_list = frm.doc.task_list.split(', ');
    }
    frappe.call({
        method: "offer_customizations.custmizations.timesheet.get_assigned_meeting",
        args: { 'emp': frm.doc.employee },
        callback: function (r) {
            let tasks = r.message;
            if (typeof tasks === "string") {
                tasks = JSON.parse(tasks); // Convert string to array
            }
            t_list = t_list.concat(tasks);
            console.log("Task List Fetched as Array:", t_list);
            dialog.set_value('task_list', t_list);
        }
    })

    offer_customizations.custmizations.timesheet.control_timer(frm, dialog, row, timestamp);
    dialog.show();
};


offer_customizations.custmizations.timesheet.control_timer = function (frm, dialog, row, timestamp = 0) {
    var $btn_start = dialog.$wrapper.find(".playpause .btn-start");
    var $btn_stop = dialog.$wrapper.find(".playpause .btn-stop")
    var $btn_complete = dialog.$wrapper.find(".playpause .btn-complete");
    var interval = null;
    var currentIncrement = timestamp;
    var initialised = row ? true : false;
    var clicked = false;
    var flag = true; // Alert only once
    // If row with not completed status, initialize timer with the time elapsed on click of 'Start Timer'.
    if (row) {
        initialised = true;
        $btn_start.hide();
        $btn_stop.show();
        $btn_complete.show();
        initialiseTimer();
    }
    if (!initialised) {
        $btn_stop.hide();
        $btn_complete.hide();
    }
    $btn_start.click(function (e) {
        if (!initialised) {
            // New activity if no activities found
            var args = dialog.get_values();
            if (!args) return;
            row = frappe.model.add_child(frm.doc, "Timesheet Detail", "time_logs");
            row.activity_type = args.activity_type;
            row.from_time = frappe.datetime.get_datetime_as_string();
            row.project = args.project;
            row.task = args.task;
            row.expected_hours = args.expected_hours;
            row.completed = 0;
            frm.refresh_field("time_logs");
            frm.save();
        }
        // ✅ Update Task status to "Working"
        if (args.task) {
            frappe.call({
                method: "frappe.client.set_value",
                args: {
                    doctype: "Task",
                    name: args.task,
                    fieldname: "status",
                    value: "Working"
                },
                callback: function (r) {
                    console.log("Response of task", r)
                    if (!r.exc) {
                        console.log("✅ Task status updated to Working");
                        frappe.show_alert({ message: __("Task marked as Working"), indicator: "green" });
                    }
                }
            });
        }
        if (clicked) {
            e.preventDefault();
            return false;
        }

        if (!initialised) {
            initialised = true;
            $btn_start.hide();
            $btn_stop.show();
            $btn_complete.show();
            initialiseTimer();
        }
    });

    //stop the timer and update the time logged by the timer on click of stop button with progress percentage
    $btn_stop.click(function () {
        var grid_row = cur_frm.fields_dict['time_logs'].grid.get_row(row.idx - 1);
        var args = dialog.get_values();
        if (args.progress_percentage < 1) {
            frappe.throw('Fill the Progress Percentage first')
        }
        grid_row.doc.progress = args.progress_percentage;
        grid_row.doc.activity_type = args.activity_type;
        grid_row.doc.project = args.project;
        grid_row.doc.task = args.task;
        grid_row.doc.expected_hours = args.expected_hours;
        grid_row.doc.hours = currentIncrement / 3600;
        grid_row.doc.to_time = frappe.datetime.now_datetime();
        grid_row.refresh();

        // ---- add progress to tasks -----
        let color = "#ffffff";
        let status = "Hold";
        if (args.progress_percentage >= 100) {
            status = "Pending Review";
            color = "#28a745"; // Green for completed
        } else if (args.progress_percentage > 50) {
            color = "#2020ff"; // Blue for >50%
        } else if (args.progress_percentage > 30) {
            color = "#ffa500"; // Orange for >30%
        } else {
            color = "#ff4d4d"; // Red for <30%
        }
        // let color = "#ffffff";

        // if (args.progress_percentage > 50) {
        //     color = "#2020ff"
        // } else if (args.progress_percentage > 30) {
        //     color = "#ffa500"
        // } else {
        //     color = "#ff4d4d"
        // }

        try {
            frappe.db.set_value("Task", args.task, {
                "progress": args.progress_percentage,
                "status": status,
                "color": color
            })
        } catch (error) {
            console.error("ERROR while updating tasks progress")
            console.error({ error })
        }

        frm.dirty()
        frm.save();
        reset();
        dialog.hide();
    })
    // Stop the timer and update the time logged by the timer on click of 'Complete' button
    $btn_complete.click(function () {
        var grid_row = cur_frm.fields_dict['time_logs'].grid.get_row(row.idx - 1);
        var args = dialog.get_values();
        grid_row.doc.completed = 1;
        grid_row.doc.activity_type = args.activity_type;
        grid_row.doc.project = args.project;
        grid_row.doc.task = args.task;
        grid_row.doc.expected_hours = args.expected_hours;
        grid_row.doc.hours = currentIncrement / 3600;
        grid_row.doc.to_time = frappe.datetime.now_datetime();
        grid_row.refresh();

        // ---- add progress to tasks -----
        let color = "#2020ff";

        try {
            frappe.db.set_value("Task", args.task, {
                "progress": 100,
                "status": "Pending Review",
                "color": color
            })
        } catch (error) {
            console.error("ERROR while updating tasks progress")
            console.error({ error })
        }


        frm.dirty()
        frm.save();
        reset();
        dialog.hide();
    });
    function initialiseTimer() {
        interval = setInterval(function () {
            var current = setCurrentIncrement();
            updateStopwatch(current);
        }, 1000);
    }

    function updateStopwatch(increment) {
        var hours = Math.floor(increment / 3600);
        var minutes = Math.floor((increment - (hours * 3600)) / 60);
        var seconds = increment - (hours * 3600) - (minutes * 60);

        // If modal is closed by clicking anywhere outside, reset the timer
        if (!$('.modal-dialog').is(':visible')) {
            reset();
        }
        if (hours > 99999)
            reset();
        if (cur_dialog && cur_dialog.get_value('expected_hours') > 0) {
            if (flag && (currentIncrement >= (cur_dialog.get_value('expected_hours') * 3600))) {
                frappe.utils.play_sound("alert");
                // frappe.msgprint(__("Timer exceeded the given hours."));
                flag = false;
            }
        }
        $(".hours").text(hours < 10 ? ("0" + hours.toString()) : hours.toString());
        $(".minutes").text(minutes < 10 ? ("0" + minutes.toString()) : minutes.toString());
        $(".seconds").text(seconds < 10 ? ("0" + seconds.toString()) : seconds.toString());
    }

    function setCurrentIncrement() {
        currentIncrement += 1;
        return currentIncrement;
    }

    function reset() {
        currentIncrement = 0;
        initialised = false;
        clearInterval(interval);
        $(".hours").text("00");
        $(".minutes").text("00");
        $(".seconds").text("00");
        $btn_complete.hide();
        $btn_start.show();
    }
};



