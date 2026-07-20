# Copyright (c) 2026, Omnexa and contributors
# License: MIT

"""Phase 6 — Read-only finance assistant and lightweight predictions."""

from __future__ import annotations

import frappe
from frappe.utils import add_days, flt, today

from omnexa_intelligence_core.finance_data_mart import get_finance_data_mart


def _predict_cashflow_30d(company: str) -> dict:
	to_date = today()
	from_date = add_days(to_date, -90)
	mart = get_finance_data_mart(company=company, from_date=from_date, to_date=to_date)
	gl = mart.get("gl") or {}
	net = flt(gl.get("total_debit")) - flt(gl.get("total_credit"))
	daily = net / 90 if net else 0
	predicted = daily * 30
	return {
		"metric": "cashflow_30d",
		"horizon_days": 30,
		"predicted_value": predicted,
		"confidence": 0.55 if abs(daily) > 0 else 0.35,
		"basis_note": "90-day JE net run-rate (heuristic MVP)"
	}


def _predict_collections_30d(company: str) -> dict:
	ar = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(outstanding_amount), 0) AS outstanding
		FROM `tabSales Invoice`
		WHERE company = %(company)s AND docstatus = 1 AND outstanding_amount > 0
		""",
		{"company": company
	},
	)[0][0]
	predicted = flt(ar) * 0.25
	return {
		"metric": "collections_30d",
		"horizon_days": 30,
		"predicted_value": predicted,
		"confidence": 0.5,
		"basis_note": "25% of open AR (heuristic MVP)"
	}


@frappe.whitelist(methods=["GET", "POST"])
def predict_finance_metrics(company: str) -> dict:
	if frappe.session.user == "Guest":
		frappe.throw("Login required.", frappe.PermissionError)
	return {
		"ok": True,
		"company": company,
		"predictions": [
			_predict_cashflow_30d(company),
			_predict_collections_30d(company),
		],
		"disclaimer": "Heuristic MVP — not audited forecast. Human approval required for actions."
	}


@frappe.whitelist(methods=["GET", "POST"])
def ask_finance_assistant(company: str, question: str, from_date: str | None = None, to_date: str | None = None) -> dict:
	"""Rule-based read-only Q&A over official finance mart (no LLM required)."""
	if frappe.session.user == "Guest":
		frappe.throw("Login required.", frappe.PermissionError)

	to_date = to_date or today()
	from_date = from_date or add_days(to_date, -30)
	mart = get_finance_data_mart(company=company, from_date=from_date, to_date=to_date)
	q = (question or "").strip().lower()
	answer = _answer_question(q, mart)
	return {
		"ok": True,
		"company": company,
		"question": question,
		"answer": answer,
		"source": "finance_data_mart",
		"safety": {"mode": "read_only", "human_approval_required_for_actions": True}
	}


def _answer_question(q: str, mart: dict) -> str:
	gl = mart.get("gl") or {}
	ar_ap = mart.get("ar_ap") or {}
	cash = mart.get("cash") or {}
	vat = mart.get("vat") or {}

	if any(k in q for k in ("مبيعات", "sales", "revenue")):
		return f"Sales total for period: {gl.get('sales_total', 0):,.2f}"
	if any(k in q for k in ("مشتريات", "purchase", "procurement")):
		return f"Purchase total for period: {gl.get('purchase_total', 0):,.2f}"
	if any(k in q for k in ("ذمم مدينة", "receivable", "ar", "عملاء")):
		return f"AR outstanding: {ar_ap.get('ar_outstanding', 0):,.2f} ({ar_ap.get('ar_open_invoices', 0)} open invoices)"
	if any(k in q for k in ("ذمم دائنة", "payable", "ap", "مورد")):
		return f"AP outstanding: {ar_ap.get('ap_outstanding', 0):,.2f} ({ar_ap.get('ap_open_invoices', 0)} open invoices)"
	if any(k in q for k in ("نقد", "cash", "bank", "بنك")):
		return f"Cash & bank balance (GL): {cash.get('cash_and_bank_balance', 0):,.2f}"
	if any(k in q for k in ("vat", "ضريبة", "قيمة مضافة")):
		return (
			f"Input VAT GL: {vat.get('input_vat_gl')} ({vat.get('input_source')}); "
			f"Output VAT GL: {vat.get('output_vat_gl')} ({vat.get('output_source')})"
		)
	return (
		f"Period KPIs — Sales: {gl.get('sales_total', 0):,.2f}, Purchases: {gl.get('purchase_total', 0):,.2f}, "
		f"AR: {ar_ap.get('ar_outstanding', 0):,.2f}, Cash: {cash.get('cash_and_bank_balance', 0):,.2f}. "
		"Ask about sales, purchases, AR, AP, cash, or VAT."
	)
