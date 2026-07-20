frappe.ui.form.on("Intelligence Action Queue", {
	refresh(frm) {
		if (frm.is_new()) return;

		const status = (frm.doc.status || "").toLowerCase();
		const canApprove = status === "pending approval";
		const canExecute = status === "approved";
		const canRollback = ["executed", "simulated"].includes(status);

		if (canApprove) {
			frm.add_custom_button(__("Approve"), async () => {
				await frappe.call({
					method: "omnexa_intelligence_core.api.approve_action",
					args: { action_id: frm.doc.name },
				});
				await frm.reload_doc();
				frappe.show_alert({ message: __("Action approved"), indicator: "green" });
			});

			frm.add_custom_button(__("Reject"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Reject Action"),
					fields: [
						{
							fieldname: "reason",
							fieldtype: "Small Text",
							label: __("Reason"),
							reqd: 1,
						},
					],
					primary_action_label: __("Reject"),
					primary_action: async (values) => {
						await frappe.call({
							method: "omnexa_intelligence_core.api.reject_action",
							args: { action_id: frm.doc.name, reason: values.reason },
						});
						d.hide();
						await frm.reload_doc();
						frappe.show_alert({ message: __("Action rejected"), indicator: "orange" });
					},
				});
				d.show();
			});
		}

		if (canExecute) {
			frm.add_custom_button(__("Execute (Dry Run)"), async () => {
				await frappe.call({
					method: "omnexa_intelligence_core.api.execute_action",
					args: { action_id: frm.doc.name, dry_run: 1 },
				});
				await frm.reload_doc();
				frappe.show_alert({ message: __("Dry run execution completed"), indicator: "blue" });
			});

			frm.add_custom_button(__("Execute"), async () => {
				await frappe.call({
					method: "omnexa_intelligence_core.api.execute_action",
					args: { action_id: frm.doc.name, dry_run: 0 },
				});
				await frm.reload_doc();
				frappe.show_alert({ message: __("Execution completed"), indicator: "green" });
			});
		}

		if (canRollback) {
			frm.add_custom_button(__("Rollback"), () => {
				const d = new frappe.ui.Dialog({
					title: __("Rollback Action"),
					fields: [
						{
							fieldname: "note",
							fieldtype: "Small Text",
							label: __("Rollback Note"),
						},
					],
					primary_action_label: __("Rollback"),
					primary_action: async (values) => {
						await frappe.call({
							method: "omnexa_intelligence_core.api.rollback_action",
							args: { action_id: frm.doc.name, note: values.note || "" },
						});
						d.hide();
						await frm.reload_doc();
						frappe.show_alert({ message: __("Rollback completed"), indicator: "orange" });
					},
				});
				d.show();
			});
		}
	},
});

