frappe.listview_settings["Intelligence Action Queue"] = {
	onload(listview) {
		const promptText = (title, label, reqd = false) =>
			new Promise((resolve) => {
				const d = new frappe.ui.Dialog({
					title,
					fields: [{ fieldname: "value", fieldtype: "Small Text", label, reqd: reqd ? 1 : 0 }],
					primary_action_label: __("Submit"),
					primary_action: (values) => {
						d.hide();
						resolve((values && values.value) || "");
					},
				});
				d.show();
			});

		const getSelected = () => {
			const rows = listview.get_checked_items() || [];
			return rows.map((r) => r.name).filter(Boolean);
		};

		const runBulk = async (label, fn) => {
			const names = getSelected();
			if (!names.length) {
				frappe.show_alert({ message: __("Select at least one action."), indicator: "orange" });
				return;
			}
			for (const name of names) {
				// eslint-disable-next-line no-await-in-loop
				await fn(name);
			}
			frappe.show_alert({ message: __("{0} completed for {1} actions.", [label, names.length]), indicator: "green" });
			listview.refresh();
		};

		listview.page.add_action_item(__("Approve Selected"), async () => {
			await runBulk(__("Approve"), (name) =>
				frappe.call({
					method: "omnexa_intelligence_core.api.approve_action",
					args: { action_id: name },
				})
			);
		});

		listview.page.add_action_item(__("Reject Selected"), async () => {
			const reason = await promptText(__("Reject Selected Actions"), __("Reason"), true);
			if (!reason) return;
			await runBulk(__("Reject"), (name) =>
				frappe.call({
					method: "omnexa_intelligence_core.api.reject_action",
					args: { action_id: name, reason },
				})
			);
		});

		listview.page.add_action_item(__("Execute Selected (Dry Run)"), async () => {
			await runBulk(__("Execute"), (name) =>
				frappe.call({
					method: "omnexa_intelligence_core.api.execute_action",
					args: { action_id: name, dry_run: 1 },
				})
			);
		});

		listview.page.add_action_item(__("Rollback Selected"), async () => {
			const note = await promptText(__("Rollback Selected Actions"), __("Rollback Note"), false);
			await runBulk(__("Rollback"), (name) =>
				frappe.call({
					method: "omnexa_intelligence_core.api.rollback_action",
					args: { action_id: name, note: note || "" },
				})
			);
		});

		listview.page.add_menu_item(__("Run Governance Cycle"), async () => {
			const d = new frappe.ui.Dialog({
				title: __("Run Governance Cycle"),
				fields: [
					{
						fieldname: "auto_approve",
						fieldtype: "Check",
						label: __("Auto approve generated actions"),
						default: 0,
					},
					{
						fieldname: "execute_dry_run",
						fieldtype: "Check",
						label: __("Execute in dry-run mode"),
						default: 1,
					},
					{
						fieldname: "execute_limit",
						fieldtype: "Int",
						label: __("Execution limit"),
						default: 25,
						reqd: 1,
					},
				],
				primary_action_label: __("Run"),
				primary_action: async (values) => {
					const r = await frappe.call({
						method: "omnexa_intelligence_core.api.run_governance_cycle",
						args: {
							auto_approve: values.auto_approve ? 1 : 0,
							execute_dry_run: values.execute_dry_run ? 1 : 0,
							execute_limit: values.execute_limit || 25,
						},
					});
					const msg = (r && r.message) || {};
					const k = msg.queue_kpis || {};
					d.hide();
					frappe.msgprint({
						title: __("Governance Cycle Result"),
						message: __(
							"Scan: {0} signals, {1} recommendations, {2} predictions<br>" +
								"Queued: {3}<br>Executed: {4}<br>" +
								"Queue KPIs -> Pending: {5}, Approved: {6}, Simulated: {7}, Executed: {8}, Failed: {9}",
							[
								((msg.scan || {}).signals_created_or_updated || 0),
								((msg.scan || {}).recommendations_created_or_updated || 0),
								((msg.scan || {}).predictions_created_or_updated || 0),
								((msg.queued || {}).created_count || 0),
								((msg.executed || {}).processed_count || 0),
								k.pending_approval || 0,
								k.approved || 0,
								k.simulated || 0,
								k.executed || 0,
								k.failed || 0,
							]
						),
						indicator: "green",
					});
					listview.refresh();
				},
			});
			d.show();
		});
	},
};

