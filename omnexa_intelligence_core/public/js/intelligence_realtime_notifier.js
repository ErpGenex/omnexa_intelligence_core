(function () {
	if (typeof frappe === "undefined") return;
	if (frappe.session && frappe.session.user === "Guest") return;
	if (window.__omnexaActionApprovalPoller) return;
	window.__omnexaActionApprovalPoller = true;

	let lastCount = null;
	let lastAlertAt = 0;
	let badgeEl = null;

	const ensureBadge = () => {
		if (badgeEl && badgeEl.parentNode) return badgeEl;
		const nav = document.querySelector(".navbar .navbar-nav") || document.querySelector(".navbar");
		if (!nav) return null;
		const container = document.createElement("li");
		container.className = "nav-item omnexa-approval-badge-wrap";
		container.style.marginLeft = "8px";
		const badge = document.createElement("span");
		badge.className = "indicator-pill orange";
		badge.style.display = "none";
		badge.style.cursor = "pointer";
		badge.title = __("Open pending approvals");
		badge.onclick = () => frappe.set_route("List", "Intelligence Action Queue", { status: "Pending Approval" });
		container.appendChild(badge);
		nav.appendChild(container);
		badgeEl = badge;
		return badgeEl;
	};

	const updateBadge = (count) => {
		const badge = ensureBadge();
		if (!badge) return;
		if (count > 0) {
			badge.style.display = "inline-block";
			badge.textContent = __("{0} Pending", [count]);
		} else {
			badge.style.display = "none";
		}
	};

	const poll = async () => {
		try {
			const r = await frappe.call({
				method: "omnexa_intelligence_core.api.get_pending_approval_count",
			});
			const count = cint((r && r.message && r.message.pending_approval_count) || 0);
			updateBadge(count);
			if (lastCount === null) {
				lastCount = count;
				return;
			}

			const now = Date.now();
			if (count > lastCount && now - lastAlertAt > 120000) {
				lastAlertAt = now;
				frappe.show_alert(
					{
						message: __("{0} actions pending approval.", [count]),
						indicator: "orange",
					},
					8
				);
			}
			lastCount = count;
		} catch (e) {
			// keep notifier silent on transient errors
		}
	};

	setTimeout(poll, 3000);
	setInterval(poll, 30000);
})();

