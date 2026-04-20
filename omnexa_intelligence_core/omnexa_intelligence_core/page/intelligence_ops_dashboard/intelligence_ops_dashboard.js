frappe.pages["intelligence-ops-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Intelligence Ops Dashboard"),
		single_column: true,
	});

	const $root = $(`
		<div class="intelligence-ops-dashboard">
			<div class="mb-3 d-flex gap-2">
				<button class="btn btn-primary btn-sm" data-action="run-cycle">${__("Run Governance Cycle")}</button>
				<button class="btn btn-secondary btn-sm" data-action="refresh">${__("Refresh")}</button>
			</div>
			<div class="mb-3 row" data-section="kpis"></div>
			<div class="mb-3" data-section="health"></div>
			<div class="row">
				<div class="col-md-6">
					<div class="card mb-3">
						<div class="card-header"><b>${__("Pending Approvals")}</b></div>
						<div class="card-body p-0">
							<table class="table table-sm mb-0">
								<thead>
									<tr>
										<th>${__("Title")}</th>
										<th>${__("Priority")}</th>
										<th>${__("Action")}</th>
									</tr>
								</thead>
								<tbody data-section="pending-rows">
									<tr><td colspan="3" class="text-muted">${__("Loading...")}</td></tr>
								</tbody>
							</table>
						</div>
					</div>
				</div>
				<div class="col-md-6">
					<div class="card mb-3">
						<div class="card-header"><b>${__("Top Recommendations")}</b></div>
						<div class="card-body p-0">
							<table class="table table-sm mb-0">
								<thead>
									<tr>
										<th>${__("Title")}</th>
										<th>${__("Priority Score")}</th>
									</tr>
								</thead>
								<tbody data-section="rec-rows">
									<tr><td colspan="2" class="text-muted">${__("Loading...")}</td></tr>
								</tbody>
							</table>
						</div>
					</div>
				</div>
			</div>
		</div>
	`);

	$(page.body).append($root);

	const kpiCard = (label, value, tone) => `
		<div class="col-md-2 col-6 mb-2">
			<div class="card border-${tone || "secondary"}">
				<div class="card-body py-2">
					<div class="small text-muted">${frappe.utils.escape_html(label)}</div>
					<div class="h5 mb-0">${frappe.utils.escape_html(String(value))}</div>
				</div>
			</div>
		</div>`;

	const render = (payload) => {
		const k = payload.queue_kpis || {};
		const d = payload.dashboard || {};
		const gov = d.governance || {};
		const health = d.health_score || 0;

		$root.find('[data-section="kpis"]').html(
			[
				kpiCard(__("Pending"), k.pending_approval || 0, "warning"),
				kpiCard(__("Approved"), k.approved || 0, "info"),
				kpiCard(__("Running"), k.running || 0, "primary"),
				kpiCard(__("Simulated"), k.simulated || 0, "secondary"),
				kpiCard(__("Executed"), k.executed || 0, "success"),
				kpiCard(__("Failed"), k.failed || 0, "danger"),
			].join("")
		);

		$root.find('[data-section="health"]').html(
			`<div class="alert alert-light mb-0">
				<b>${__("Health Score")}:</b> ${health}
				&nbsp;|&nbsp;
				<b>${__("Governance Score")}:</b> ${gov.score || 0}
				&nbsp;|&nbsp;
				<b>${__("Risk Level")}:</b> ${frappe.utils.escape_html(gov.risk_level || "n/a")}
			</div>`
		);

		const pendingRows = (payload.pending_actions || []).map(
			(row) => `
			<tr>
				<td>${frappe.utils.escape_html(row.title || "")}</td>
				<td>${frappe.utils.escape_html(row.priority || "")}</td>
				<td>
					<button class="btn btn-xs btn-outline-primary" data-open="${frappe.utils.escape_html(row.name)}">${__("Open")}</button>
				</td>
			</tr>`
		);
		$root
			.find('[data-section="pending-rows"]')
			.html(pendingRows.length ? pendingRows.join("") : `<tr><td colspan="3" class="text-muted">${__("No pending approvals.")}</td></tr>`);

		const recRows = (d.recommendations || []).slice(0, 8).map(
			(row) => `
			<tr>
				<td>${frappe.utils.escape_html(row.title || "")}</td>
				<td>${frappe.utils.escape_html(String(row.priority_score || 0))}</td>
			</tr>`
		);
		$root
			.find('[data-section="rec-rows"]')
			.html(recRows.length ? recRows.join("") : `<tr><td colspan="2" class="text-muted">${__("No recommendations.")}</td></tr>`);
	};

	const refreshData = async () => {
		const r = await frappe.call({
			method: "omnexa_intelligence_core.api.get_ops_dashboard_payload",
		});
		render((r && r.message) || {});
	};

	const runCycle = async () => {
		const d = new frappe.ui.Dialog({
			title: __("Run Governance Cycle"),
			fields: [
				{ fieldname: "auto_approve", fieldtype: "Check", label: __("Auto approve generated actions"), default: 1 },
				{ fieldname: "execute_dry_run", fieldtype: "Check", label: __("Execute in dry-run mode"), default: 1 },
				{ fieldname: "execute_limit", fieldtype: "Int", label: __("Execution limit"), default: 25, reqd: 1 },
			],
			primary_action_label: __("Run"),
			primary_action: async (values) => {
				await frappe.call({
					method: "omnexa_intelligence_core.api.run_governance_cycle",
					args: {
						auto_approve: values.auto_approve ? 1 : 0,
						execute_dry_run: values.execute_dry_run ? 1 : 0,
						execute_limit: values.execute_limit || 25,
					},
				});
				d.hide();
				frappe.show_alert({ message: __("Governance cycle completed."), indicator: "green" });
				await refreshData();
			},
		});
		d.show();
	};

	$root.on("click", '[data-action="refresh"]', () => refreshData());
	$root.on("click", '[data-action="run-cycle"]', () => runCycle());
	$root.on("click", "[data-open]", function () {
		const name = $(this).attr("data-open");
		if (!name) return;
		frappe.set_route("Form", "Intelligence Action Queue", name);
	});

	refreshData();
};

