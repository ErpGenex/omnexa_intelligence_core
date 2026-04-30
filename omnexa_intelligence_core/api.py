# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

from __future__ import annotations

import frappe

from omnexa_intelligence_core.engine.analyzers import run_core_analyzers
from omnexa_setup_intelligence.api import get_executive_governance_summary

_ACTION_QUEUE_DOCTYPE = "Intelligence Action Queue"


def _action_queue_table_ready() -> bool:
	"""False during fresh install / setup wizard before tabIntelligence Action Queue exists."""
	try:
		return bool(frappe.db and frappe.db.table_exists(_ACTION_QUEUE_DOCTYPE))
	except Exception:
		return False


def _severity_weight(severity: str) -> int:
	sev = (severity or "").lower()
	if sev == "critical":
		return 100
	if sev == "high":
		return 75
	if sev == "medium":
		return 45
	return 20


def _recommendation_priority(rec: dict, signal_map: dict[str, dict]) -> int:
	conf = float(rec.get("confidence") or 0)
	conf_score = min(100, int(conf * 100))
	status = (rec.get("status") or "").lower()
	status_penalty = 25 if status in {"accepted", "rejected"} else 0
	sig = signal_map.get((rec.get("title") or "").lower(), {})
	sev_score = _severity_weight(sig.get("severity")) if sig else 40
	return max(0, min(100, int((conf_score * 0.6) + (sev_score * 0.4) - status_penalty)))


def _benchmark_profile(governance_score: int) -> dict:
	if governance_score >= 85:
		label = "top_quartile"
		gap = 0
	elif governance_score >= 70:
		label = "upper_mid"
		gap = 85 - governance_score
	elif governance_score >= 50:
		label = "developing"
		gap = 70 - governance_score
	else:
		label = "at_risk"
		gap = 50 - governance_score
	return {"tier": label, "target_gap_points": max(0, gap)}


def _build_playbooks(predictions: list[dict]) -> list[dict]:
	by_metric = {(p.get("metric") or "").lower(): p for p in (predictions or [])}
	playbooks = []
	cf = float((by_metric.get("cashflow_30d") or {}).get("predicted_value") or 0)
	ip = float((by_metric.get("inventory_pressure_30d") or {}).get("predicted_value") or 0)
	if cf < 0:
		playbooks.append(
			{
				"id": "cash_protection",
				"title": "Cash Protection Playbook",
				"priority": "critical",
				"steps": [
					"Freeze discretionary spending approvals for 14 days.",
					"Run top-20 overdue receivables collection sprint.",
					"Rephase non-critical supplier payments.",
				],
			}
		)
	if ip >= 35:
		playbooks.append(
			{
				"id": "inventory_continuity",
				"title": "Inventory Continuity Playbook",
				"priority": "high",
				"steps": [
					"Raise replenishment requests for fast-moving SKUs.",
					"Increase safety stock for constrained items.",
					"Enable weekly supplier ETA review cadence.",
				],
			}
		)
	if not playbooks:
		playbooks.append(
			{
				"id": "steady_state",
				"title": "Steady-State Optimization Playbook",
				"priority": "medium",
				"steps": [
					"Review forecast drift and confidence weekly.",
					"Optimize working-capital cycle by 3-5%.",
					"Track top 5 process bottlenecks.",
				],
			}
		)
	return playbooks


def _enqueue_action(playbook: dict, step: str, source: str = "dashboard") -> str:
	if not _action_queue_table_ready():
		frappe.throw(
			"Intelligence Action Queue is not installed yet. Complete setup / migrate and retry.",
			frappe.ValidationError,
		)
	title = f"{playbook.get('id')}: {step}"
	name = frappe.db.get_value(
		_ACTION_QUEUE_DOCTYPE,
		{"title": title, "status": ["in", ["Pending Approval", "Approved", "Queued"]]},
		"name",
	)
	if name:
		return name
	doc = frappe.get_doc(
		{
			"doctype": _ACTION_QUEUE_DOCTYPE,
			"title": title,
			"playbook_id": playbook.get("id"),
			"priority": playbook.get("priority") or "medium",
			"status": "Pending Approval",
			"source": source,
			"rollback_status": "Not Requested",
			"payload_json": frappe.as_json({"step": step, "playbook": playbook.get("title")}),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _append_audit_log(doc, message: str):
	now = frappe.utils.now_datetime()
	entry = f"{now.isoformat()} | {message}"
	base = (doc.execution_log or "").strip()
	doc.execution_log = f"{base}\n{entry}".strip()


def _queue_kpis() -> dict:
	if not _action_queue_table_ready():
		return {
			"pending_approval": 0,
			"approved": 0,
			"running": 0,
			"simulated": 0,
			"executed": 0,
			"failed": 0,
		}
	dt = _ACTION_QUEUE_DOCTYPE
	return {
		"pending_approval": int(frappe.db.count(dt, {"status": "Pending Approval"})),
		"approved": int(frappe.db.count(dt, {"status": "Approved"})),
		"running": int(frappe.db.count(dt, {"status": "Running"})),
		"simulated": int(frappe.db.count(dt, {"status": "Simulated"})),
		"executed": int(frappe.db.count(dt, {"status": "Executed"})),
		"failed": int(frappe.db.count(dt, {"status": "Failed"})),
	}


@frappe.whitelist(methods=["POST"])
def run_intelligence_scan():
	"""Run analyzer pass and return recent signals/recommendations summary."""
	if "System Manager" not in (frappe.get_roles() or []):
		frappe.throw("Not permitted", frappe.PermissionError)

	result = run_core_analyzers()
	return {"ok": True, **result}


@frappe.whitelist(methods=["POST"])
def get_executive_intelligence_dashboard():
	"""Unified executive payload for governance + intelligence outputs."""
	if frappe.session.user == "Guest":
		frappe.throw("Login required.", frappe.PermissionError)

	gov = get_executive_governance_summary()
	signals = frappe.get_all(
		"Intelligence Signal",
		fields=["name", "title", "signal_type", "severity", "workspace", "modified", "evidence_json"],
		order_by="modified desc",
		limit=10,
	)
	recommendations = frappe.get_all(
		"Intelligence Recommendation",
		fields=["name", "title", "status", "confidence", "expected_impact", "action_route", "modified"],
		order_by="modified desc",
		limit=10,
	)
	predictions = frappe.get_all(
		"Prediction Snapshot",
		fields=["name", "metric", "horizon_days", "predicted_value", "confidence", "basis_note", "modified"],
		order_by="modified desc",
		limit=10,
	)
	signal_map = {(s.get("title") or "").lower(): s for s in signals}
	for r in recommendations:
		r["priority_score"] = _recommendation_priority(r, signal_map)
	recommendations = sorted(recommendations, key=lambda x: x.get("priority_score", 0), reverse=True)

	gov_score = int((gov or {}).get("score") or 0)
	benchmark = _benchmark_profile(gov_score)
	health_score = max(0, min(100, gov_score - max(0, (len(signals) - 2) * 4)))

	return {
		"ok": True,
		"governance": gov,
		"health_score": health_score,
		"benchmark": benchmark,
		"signals": signals,
		"recommendations": recommendations,
		"predictions": predictions,
		"playbooks": _build_playbooks(predictions),
	}


@frappe.whitelist(methods=["POST"])
def enqueue_playbook_actions(auto_approve: int | str = 0):
	"""Create actionable queue items from current dashboard playbooks."""
	if "System Manager" not in (frappe.get_roles() or []):
		frappe.throw("Not permitted", frappe.PermissionError)
	if not _action_queue_table_ready():
		return {"ok": True, "created_count": 0, "action_ids": []}

	dashboard = get_executive_intelligence_dashboard()
	playbooks = dashboard.get("playbooks") or []
	created = []
	for pb in playbooks:
		for step in pb.get("steps") or []:
			created.append(_enqueue_action(pb, step, source="auto_playbook"))
	if int(auto_approve or 0) == 1 and created:
		for action_id in created:
			approve_action(action_id)
	return {"ok": True, "created_count": len(created), "action_ids": created}


@frappe.whitelist(methods=["POST"])
def approve_action(action_id: str):
	if "System Manager" not in (frappe.get_roles() or []):
		frappe.throw("Not permitted", frappe.PermissionError)
	doc = frappe.get_doc(_ACTION_QUEUE_DOCTYPE, action_id)
	if doc.status in {"Executed", "Simulated", "Cancelled"}:
		return {"ok": True, "name": doc.name, "status": doc.status}
	doc.status = "Approved"
	doc.approved_by = frappe.session.user
	doc.approved_on = frappe.utils.now_datetime()
	_append_audit_log(doc, f"approved by {frappe.session.user}")
	doc.save(ignore_permissions=True)
	return {"ok": True, "name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def reject_action(action_id: str, reason: str | None = None):
	if "System Manager" not in (frappe.get_roles() or []):
		frappe.throw("Not permitted", frappe.PermissionError)
	doc = frappe.get_doc(_ACTION_QUEUE_DOCTYPE, action_id)
	doc.status = "Rejected"
	_append_audit_log(doc, f"rejected by {frappe.session.user}; reason={reason or 'n/a'}")
	doc.save(ignore_permissions=True)
	return {"ok": True, "name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def execute_pending_actions(dry_run: int | str = 1, limit: int | str = 10):
	"""Execute queued actions in controlled mode; currently supports safe simulated execution."""
	if "System Manager" not in (frappe.get_roles() or []):
		frappe.throw("Not permitted", frappe.PermissionError)

	is_dry = int(dry_run or 1) == 1
	lim = max(1, min(100, int(limit or 10)))
	if not _action_queue_table_ready():
		return {"ok": True, "processed_count": 0, "action_ids": [], "dry_run": is_dry}
	rows = frappe.get_all(
		_ACTION_QUEUE_DOCTYPE,
		filters={"status": "Approved"},
		fields=["name", "title", "payload_json", "priority"],
		order_by="creation asc",
		limit=lim,
	)
	done = []
	for row in rows:
		doc = frappe.get_doc(_ACTION_QUEUE_DOCTYPE, row.get("name"))
		try:
			doc.status = "Running"
			_append_audit_log(doc, f"execution started by {frappe.session.user}")
			doc.save(ignore_permissions=True)
			if is_dry:
				doc.status = "Simulated"
				_append_audit_log(doc, "dry-run simulated execution completed")
			else:
				# Safety-first: keep deterministic no-side-effect execution for now.
				doc.status = "Executed"
				_append_audit_log(doc, "execution completed (safe mode)")
			doc.executed_on = frappe.utils.now_datetime()
			doc.save(ignore_permissions=True)
			done.append(doc.name)
		except Exception as ex:
			doc.status = "Failed"
			doc.last_error = str(ex)
			_append_audit_log(doc, f"execution failed: {str(ex)}")
			doc.save(ignore_permissions=True)
	return {"ok": True, "processed_count": len(done), "action_ids": done, "dry_run": is_dry}


@frappe.whitelist(methods=["POST"])
def execute_action(action_id: str, dry_run: int | str = 1):
	"""Execute one approved action by id."""
	if "System Manager" not in (frappe.get_roles() or []):
		frappe.throw("Not permitted", frappe.PermissionError)
	doc = frappe.get_doc(_ACTION_QUEUE_DOCTYPE, action_id)
	if doc.status != "Approved":
		return {"ok": False, "message": "Action must be Approved before execution.", "status": doc.status}
	is_dry = int(dry_run or 1) == 1
	try:
		doc.status = "Running"
		_append_audit_log(doc, f"execution started by {frappe.session.user}")
		doc.save(ignore_permissions=True)
		if is_dry:
			doc.status = "Simulated"
			_append_audit_log(doc, "dry-run simulated execution completed")
		else:
			doc.status = "Executed"
			_append_audit_log(doc, "execution completed (safe mode)")
		doc.executed_on = frappe.utils.now_datetime()
		doc.save(ignore_permissions=True)
		return {"ok": True, "name": doc.name, "status": doc.status, "dry_run": is_dry}
	except Exception as ex:
		doc.status = "Failed"
		doc.last_error = str(ex)
		_append_audit_log(doc, f"execution failed: {str(ex)}")
		doc.save(ignore_permissions=True)
		return {"ok": False, "name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def rollback_action(action_id: str, note: str | None = None):
	"""Safe rollback hook for executed/simulated actions."""
	if "System Manager" not in (frappe.get_roles() or []):
		frappe.throw("Not permitted", frappe.PermissionError)
	doc = frappe.get_doc(_ACTION_QUEUE_DOCTYPE, action_id)
	if doc.status not in {"Executed", "Simulated"}:
		return {"ok": False, "message": "Only executed/simulated actions can be rolled back."}
	try:
		doc.rollback_status = "Requested"
		_append_audit_log(doc, f"rollback requested by {frappe.session.user}")
		# Hook point: future real rollback action logic.
		doc.rollback_status = "Rolled Back"
		doc.rollback_ref = f"RB-{frappe.generate_hash(length=8)}"
		_append_audit_log(doc, f"rollback completed; ref={doc.rollback_ref}; note={note or 'n/a'}")
		doc.save(ignore_permissions=True)
		return {"ok": True, "name": doc.name, "rollback_status": doc.rollback_status, "rollback_ref": doc.rollback_ref}
	except Exception as ex:
		doc.rollback_status = "Rollback Failed"
		doc.last_error = str(ex)
		_append_audit_log(doc, f"rollback failed: {str(ex)}")
		doc.save(ignore_permissions=True)
		return {"ok": False, "name": doc.name, "rollback_status": doc.rollback_status}


@frappe.whitelist(methods=["GET", "POST"])
def get_pending_approval_count():
	if frappe.session.user == "Guest":
		frappe.throw("Login required.", frappe.PermissionError)
	if not _action_queue_table_ready():
		return {"ok": True, "pending_approval_count": 0}
	count = frappe.db.count(_ACTION_QUEUE_DOCTYPE, filters={"status": "Pending Approval"})
	return {"ok": True, "pending_approval_count": int(count)}


@frappe.whitelist(methods=["POST"])
def run_governance_cycle(auto_approve: int | str = 0, execute_dry_run: int | str = 1, execute_limit: int | str = 25):
	"""Single-shot operational cycle for executives.

	Steps: analyze -> build action queue -> optionally approve -> execute approved actions.
	"""
	if "System Manager" not in (frappe.get_roles() or []):
		frappe.throw("Not permitted", frappe.PermissionError)

	scan = run_core_analyzers()
	queued = enqueue_playbook_actions(auto_approve=auto_approve)
	executed = execute_pending_actions(dry_run=execute_dry_run, limit=execute_limit)
	dashboard = get_executive_intelligence_dashboard()

	return {
		"ok": True,
		"scan": scan,
		"queued": queued,
		"executed": executed,
		"queue_kpis": _queue_kpis(),
		"dashboard": dashboard,
	}


@frappe.whitelist(methods=["GET", "POST"])
def get_ops_dashboard_payload():
	"""Payload for intelligence operations desk page."""
	if frappe.session.user == "Guest":
		frappe.throw("Login required.", frappe.PermissionError)
	dashboard = get_executive_intelligence_dashboard()
	if not _action_queue_table_ready():
		pending_actions = []
	else:
		pending_actions = frappe.get_all(
			_ACTION_QUEUE_DOCTYPE,
			filters={"status": "Pending Approval"},
			fields=["name", "title", "priority", "source", "creation"],
			order_by="creation asc",
			limit=20,
		)
	return {
		"ok": True,
		"queue_kpis": _queue_kpis(),
		"dashboard": dashboard,
		"pending_actions": pending_actions,
	}

