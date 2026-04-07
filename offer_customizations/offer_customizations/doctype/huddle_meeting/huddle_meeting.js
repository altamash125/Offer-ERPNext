
frappe.ui.form.on('Huddle Meeting', {
    //     frm.clear_table("tasks_to_discuss");
    //     frm.refresh_field("tasks_to_discuss")
    // },
    
    refresh(frm) {
        frm.fields_dict["tasks_to_discuss"].grid.cannot_add_rows = true;

        // Optionally hide the "Add Multiple" button too
        frm.fields_dict["tasks_to_discuss"].grid.wrapper
            .find('.grid-add-row').hide();
        frm.fields_dict["tasks_to_discuss"].grid.wrapper
            .find('.grid-add-multiple-rows').hide();

        if (cur_frm.doc.date == frappe.datetime.now_date() && !frm.doc.__islocal) {
            let pending_task_creation = false
            $.each(frm.doc.task_to_be_created || [], function (i, row) {
                if (!row.task) {
                    pending_task_creation = true
                }
            })

            if (!frm.doc.__islocal) {
                frm.add_custom_button('Update Timesheets', function () {
                    frm.call('update_timesheets')
                })
            }
        }
        if (frm.is_new() && !frm.doc.date) {
            frm.set_value("date", frappe.datetime.get_today());
        }

        if (!frm.doc.user || !frm.doc.date) {
            return;  // Skip validation if user or date is not set
        }




    },



    get_tasks: function (frm) {
        if (!frm.doc.user) {
            frappe.msgprint(__('Please select a User first'));
            return;
        }



        frm.call({
            method: 'get_tasks',
            doc: frm.doc,
            freeze: true,
            freeze_message: __('Fetching tasks...'),
            callback: function (r) {
                if (!r.exc) {
                    console.log(r)
                    frm.refresh_field('tasks_to_discuss');
                    if (r.message && r.message.tasks_added > 0) {

                        frappe.show_alert({
                            message: __('Added {0} tasks successfully', [r.message.tasks_added]),
                            indicator: 'green'
                        }, 3);
                    } else {
                        frappe.show_alert({
                            message: __('No tasks found for the selected criteria'),
                            indicator: 'orange'
                        }, 3);
                    }
                }
            }
        });
    }
});