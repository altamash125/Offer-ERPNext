frappe.ui.form.on('Timesheet', {
    onload_post_render: function(frm) {
        render_task_summary(frm);
    },
    time_logs_on_form_rendered: function(frm) {
        render_task_summary(frm);
    },
    validate: function(frm) {
        render_task_summary(frm);
    }
});

function format_date_dd_mm_yy(datetime_str) {
    if (!datetime_str) return '';
    const date = frappe.datetime.str_to_obj(datetime_str);
    return `${String(date.getDate()).padStart(2, '0')}--${String(date.getMonth() + 1).padStart(2, '0')}--${String(date.getFullYear()).slice(-2)}`;
}

function render_task_summary(frm) {
    if (!frm.doc.time_logs || frm.doc.time_logs.length === 0) {
        frm.fields_dict.custom_task_summary_details.$wrapper.html("<p style='color: #999;'>No tasks added.</p>");
        return;
    }

    const unique_tasks = new Map();
    let total_hours = 0;

    // Step 1: Group by unique Task ID
    frm.doc.time_logs.forEach(row => {
        if (!row.task) return;

        total_hours += row.hours || 0;

        if (!unique_tasks.has(row.task)) {
            unique_tasks.set(row.task, {
                project: row.project,
                employee: row.employee,
                task: row.task,
                expected_hours: row.expected_hours || 0,
                entries: [],
                subject:row.subject,
            });
        }
        unique_tasks.get(row.task).entries.push(row);
    });

    const task_promises = [];

    // Step 2: Fetch description for each unique task
    unique_tasks.forEach((task_data, task_id) => {
        const promise = frappe.db.get_doc('Task', task_id).then(task_doc => {
            task_data.description = task_doc.description || '';
        }).catch(() => {
            task_data.description = '<i>Unable to load task description</i>';
        });
        task_promises.push(promise);
    });

    // Step 3: Once all descriptions are fetched, render HTML
    Promise.all(task_promises).then(() => {
        let html = `<div style="font-family: 'Segoe UI', Roboto, sans-serif; font-size: 14px; color: #333;">`;
        let employee_name = frm.doc.employee_name || "N/A";
        let task_index = 1;

        unique_tasks.forEach(task_data => {
            const any_entry = task_data.entries[0];
            const status = any_entry.completed ? "✅ Completed" : "⏳ In Progress";
            const status_color = any_entry.completed ? "#38a169" : "#f6ad55";

            html += `
                <div style="background: #f9fbff; border-left: 4px solid #4c9aff; padding: 15px 20px; margin-bottom: 20px; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,0.05);">
                    <h4 style="margin: 0 0 10px 0; color: #3366cc;">📝 Task ${task_index++}</h4>

                    <p><strong>Project Name:</strong> 
                        ${task_data.project ? `<a href="http://127.0.0.1:8000/app/project/${task_data.project}" target="_blank" style="color: #007bff;">${task_data.project}</a>` : 'N/A'}
                    </p>

                    <p><strong>Employee Name:</strong> 
                        ${task_data.employee ? `<a href="http://127.0.0.1:8000/app/employee/${task_data.employee}" target="_blank" style="color: #6f42c1;">${employee_name}</a>` : employee_name}
                    </p>

                    <p><strong>Task:</strong> 
                        <a href="http://127.0.0.1:8000/app/task/${task_data.task}" target="_blank" style="color: #007bff;">${task_data.task}</a>
                    </p>

                    <p><strong>Expected Hours:</strong> ${task_data.expected_hours}</p>
                    <p><strong>Subject:</strong> ${task_data.subject}</p>
                    <p><strong>Status:</strong> <span style="color: ${status_color}; font-weight: 600;">${status}</span></p>

                    <p><strong>Description :</strong></p>
                    <div style="background-color: #ffffff; border-radius: 6px; padding: 12px; border: 1px solid #eee; color: #444; margin-top: 5px;">
                        ${task_data.description}
                    </div>
                </div>
            `;
        });

        html += `<p style="margin-top: 20px; font-weight: bold; font-size: 15px; color: #2b6cb0;">🔢 Total Hours Logged: ${total_hours.toFixed(2)}</p></div>`;
        frm.fields_dict.custom_task_summary_details.$wrapper.html(html);
    });
}







