# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

from __future__ import annotations

from datetime import date, timedelta

import frappe


def _upsert_signal(signal_type: str, title: str, severity: str, workspace: str, evidence_json: str):
	name = frappe.db.get_value(
		"Intelligence Signal",
		{"signal_type": signal_type, "title": title},
		"name",
	)
	values = {
		"signal_type": signal_type,
		"title": title,
		"severity": severity,
		"workspace": workspace,
		"evidence_json": evidence_json,
	}
	if name:
		doc = frappe.get_doc("Intelligence Signal", name)
		doc.update(values)
		doc.save(ignore_permissions=True)
		return doc.name
	doc = frappe.get_doc({"doctype": "Intelligence Signal", **values})
	doc.insert(ignore_permissions=True)
	return doc.name


def _upsert_recommendation(title: str, reason: str, expected_impact: str, confidence: float, action_route: str):
	name = frappe.db.get_value("Intelligence Recommendation", {"title": title}, "name")
	values = {
		"title": title,
		"reason": reason,
		"expected_impact": expected_impact,
		"confidence": confidence,
		"action_route": action_route,
		"status": "New",
	}
	if name:
		doc = frappe.get_doc("Intelligence Recommendation", name)
		doc.update(values)
		doc.save(ignore_permissions=True)
		return doc.name
	doc = frappe.get_doc({"doctype": "Intelligence Recommendation", **values})
	doc.insert(ignore_permissions=True)
	return doc.name


def _upsert_prediction(metric: str, horizon_days: int, predicted_value: float, confidence: float, basis_note: str):
	name = frappe.db.get_value(
		"Prediction Snapshot",
		{"metric": metric, "horizon_days": horizon_days},
		"name",
	)
	values = {
		"metric": metric,
		"horizon_days": horizon_days,
		"predicted_value": float(predicted_value or 0),
		"confidence": float(confidence or 0),
		"basis_note": basis_note,
	}
	if name:
		doc = frappe.get_doc("Prediction Snapshot", name)
		doc.update(values)
		doc.save(ignore_permissions=True)
		return doc.name
	doc = frappe.get_doc({"doctype": "Prediction Snapshot", **values})
	doc.insert(ignore_permissions=True)
	return doc.name


def _calibrate_confidence(base_conf: float, metric: str, data_points: int) -> float:
	"""Confidence calibration based on data sufficiency and metric stability assumptions."""
	conf = float(base_conf or 0)
	if data_points < 5:
		conf -= 0.08
	elif data_points < 15:
		conf -= 0.03
	elif data_points > 60:
		conf += 0.04
	if metric in {"inventory_pressure_30d"}:
		# pressure index is more heuristic than direct financial totals
		conf -= 0.02
	return max(0.35, min(0.92, conf))


def _forecast_revenue_30d() -> tuple[float, float, str]:
	"""Simple baseline forecast: trailing 90-day average daily sales * 30.

	Kept intentionally transparent and auditable; can be replaced later with ML models.
	"""
	from_dt = (date.today() - timedelta(days=90)).isoformat()
	rows = frappe.db.sql(
		"""
		select coalesce(sum(base_grand_total), 0) as total, count(*) as cnt
		from `tabSales Invoice`
		where docstatus = 1 and posting_date >= %(from_dt)s
		""",
		{"from_dt": from_dt},
		as_dict=True,
	)
	total = float((rows[0] or {}).get("total") or 0)
	cnt = int((rows[0] or {}).get("cnt") or 0)
	# assume business activity spread over 90-day window
	daily = total / 90.0
	pred = daily * 30.0
	# confidence rises with observation count
	conf = 0.55 if cnt < 5 else 0.68 if cnt < 20 else 0.78
	note = f"baseline: trailing 90-day average (invoice_count={cnt})"
	return pred, conf, note, cnt


def _forecast_cashflow_30d() -> tuple[float, float, str, int]:
	"""Baseline cashflow projection: invoiced sales minus invoiced purchases (30d window)."""
	from_dt = (date.today() - timedelta(days=30)).isoformat()
	rows = frappe.db.sql(
		"""
		select
			coalesce((select sum(base_grand_total) from `tabSales Invoice` where docstatus = 1 and posting_date >= %(from_dt)s), 0) as inflow,
			coalesce((select sum(base_grand_total) from `tabPurchase Invoice` where docstatus = 1 and posting_date >= %(from_dt)s), 0) as outflow,
			coalesce((select count(*) from `tabSales Invoice` where docstatus = 1 and posting_date >= %(from_dt)s), 0) as si_cnt,
			coalesce((select count(*) from `tabPurchase Invoice` where docstatus = 1 and posting_date >= %(from_dt)s), 0) as pi_cnt
		""",
		{"from_dt": from_dt},
		as_dict=True,
	)
	row = rows[0] if rows else {}
	inflow = float(row.get("inflow") or 0)
	outflow = float(row.get("outflow") or 0)
	si_cnt = int(row.get("si_cnt") or 0)
	pi_cnt = int(row.get("pi_cnt") or 0)
	pred = inflow - outflow
	sample = si_cnt + pi_cnt
	conf = 0.52 if sample < 6 else 0.66 if sample < 20 else 0.76
	note = f"baseline: 30d invoiced inflow-outflow (si={si_cnt}, pi={pi_cnt})"
	return pred, conf, note, sample


def _forecast_inventory_pressure_30d() -> tuple[float, float, str, int]:
	"""Pressure index heuristic: demand docs vs supply docs in trailing 30 days."""
	from_dt = (date.today() - timedelta(days=30)).isoformat()
	rows = frappe.db.sql(
		"""
		select
			coalesce((select count(*) from `tabSales Invoice` where docstatus = 1 and posting_date >= %(from_dt)s), 0) as demand_docs,
			coalesce((select count(*) from `tabPurchase Invoice` where docstatus = 1 and posting_date >= %(from_dt)s), 0) as supply_docs
		""",
		{"from_dt": from_dt},
		as_dict=True,
	)
	row = rows[0] if rows else {}
	demand = float(row.get("demand_docs") or 0)
	supply = float(row.get("supply_docs") or 0)
	pressure = 0.0 if demand <= 0 else max(0.0, (demand - supply) / max(demand, 1.0)) * 100.0
	conf = 0.50 if demand + supply < 8 else 0.64 if demand + supply < 25 else 0.74
	note = f"heuristic: document imbalance demand-supply (demand={int(demand)}, supply={int(supply)})"
	return pressure, conf, note, int(demand + supply)


def _emit_risk_escalation(signals: list[str], recommendations: list[str], predictions: dict[str, float]):
	"""Escalate risk levels and attach playbook recommendations when thresholds are breached."""
	cashflow = float(predictions.get("cashflow_30d") or 0)
	pressure = float(predictions.get("inventory_pressure_30d") or 0)

	if cashflow < 0:
		signals.append(
			_upsert_signal(
				"cashflow_negative_projection",
				"Projected cashflow is negative for next 30 days",
				"critical",
				"Accounts",
				f'{{"metric":"cashflow_30d","value":{cashflow}}}',
			)
		)
		recommendations.append(
			_upsert_recommendation(
				"Activate cash protection playbook",
				"Forecast indicates net negative cashflow in the next 30 days.",
				"Protects liquidity by prioritizing collections and deferring non-critical outflows.",
				0.87,
				"/app/accounts-receivable",
			)
		)

	if pressure >= 35:
		signals.append(
			_upsert_signal(
				"inventory_pressure_escalation",
				"Inventory pressure rising (demand outpacing supply)",
				"high",
				"Inventory",
				f'{{"metric":"inventory_pressure_30d","value":{pressure}}}',
			)
		)
		recommendations.append(
			_upsert_recommendation(
				"Activate inventory continuity playbook",
				"Inventory pressure index crossed threshold; demand trend is ahead of supply trend.",
				"Reduces stockout probability and improves service level consistency.",
				0.83,
				"/app/material-request",
			)
		)


def run_core_analyzers() -> dict:
	"""Starter analyzer set: cash warning, inventory readiness, sales activation."""
	signals = []
	recommendations = []
	predictions = []

	customer_count = int(frappe.db.count("Customer"))
	item_count = int(frappe.db.count("Item"))
	warehouse_count = int(frappe.db.count("Warehouse"))
	si_count = int(frappe.db.count("Sales Invoice"))
	pi_count = int(frappe.db.count("Purchase Invoice"))

	# 1) Sales activation
	if customer_count == 0:
		signals.append(
			_upsert_signal(
				"master_gap",
				"Customer base not initialized",
				"high",
				"Sales",
				'{"metric":"count.Customer","value":0}',
			)
		)
		recommendations.append(
			_upsert_recommendation(
				"Initialize customer master",
				"No customer records found. Sales cycle cannot start without customer masters.",
				"Enables quoting/invoicing and improves revenue activation readiness.",
				0.96,
				"/app/customer",
			)
		)

	# 2) Inventory readiness
	if item_count == 0 or warehouse_count == 0:
		signals.append(
			_upsert_signal(
				"inventory_readiness_gap",
				"Inventory setup incomplete",
				"high",
				"Inventory",
				f'{{"count.Item":{item_count},"count.Warehouse":{warehouse_count}}}',
			)
		)
		recommendations.append(
			_upsert_recommendation(
				"Complete inventory setup",
				"Items or Warehouses are missing; stock movement and valuation cannot operate correctly.",
				"Reduces stockout risk and enables inventory valuation workflow.",
				0.93,
				"/app/warehouse",
			)
		)

	# 3) Early finance signal
	if si_count == 0 and pi_count == 0:
		signals.append(
			_upsert_signal(
				"finance_activation_gap",
				"Financial transaction flow not started",
				"medium",
				"Accounts",
				'{"count.Sales Invoice":0,"count.Purchase Invoice":0}',
			)
		)
		recommendations.append(
			_upsert_recommendation(
				"Post first financial transactions",
				"No sales or purchase invoices detected; financial trend analytics are not yet available.",
				"Bootstraps revenue/cost signals and enables cash-flow forecasting baseline.",
				0.88,
				"/app/sales-invoice",
			)
		)

	# 4) Revenue baseline forecast (30 days)
	rev_pred, rev_conf, rev_note, rev_points = _forecast_revenue_30d()
	rev_conf = _calibrate_confidence(rev_conf, "revenue_30d", rev_points)
	predictions.append(_upsert_prediction("revenue_30d", 30, rev_pred, rev_conf, rev_note))

	# 5) Cash shortage heuristic warning based on invoice activity imbalance
	if pi_count > 0 and si_count == 0:
		signals.append(
			_upsert_signal(
				"cash_risk_warning",
				"Potential cash-flow pressure",
				"high",
				"Accounts",
				f'{{"sales_invoices":{si_count},"purchase_invoices":{pi_count}}}',
			)
		)
		recommendations.append(
			_upsert_recommendation(
				"Review outgoing commitments vs incoming sales",
				"Purchases are being posted with no sales invoices detected; monitor liquidity exposure.",
				"Helps prevent short-term cash deficits and improves payment planning.",
				0.82,
				"/app/purchase-invoice",
			)
		)

	# 6) Cashflow baseline forecast (30 days)
	cf_pred, cf_conf, cf_note, cf_points = _forecast_cashflow_30d()
	cf_conf = _calibrate_confidence(cf_conf, "cashflow_30d", cf_points)
	predictions.append(_upsert_prediction("cashflow_30d", 30, cf_pred, cf_conf, cf_note))

	# 7) Inventory pressure forecast index (30 days, 0-100)
	ip_pred, ip_conf, ip_note, ip_points = _forecast_inventory_pressure_30d()
	ip_conf = _calibrate_confidence(ip_conf, "inventory_pressure_30d", ip_points)
	predictions.append(_upsert_prediction("inventory_pressure_30d", 30, ip_pred, ip_conf, ip_note))

	_emit_risk_escalation(
		signals,
		recommendations,
		{
			"cashflow_30d": cf_pred,
			"inventory_pressure_30d": ip_pred,
		},
	)

	return {
		"signals_created_or_updated": len(signals),
		"recommendations_created_or_updated": len(recommendations),
		"predictions_created_or_updated": len(predictions),
		"signal_ids": signals,
		"recommendation_ids": recommendations,
		"prediction_ids": predictions,
	}

