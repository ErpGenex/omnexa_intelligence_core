# Copyright (c) 2026, Omnexa and contributors
# License: MIT

"""Phase 5 — Finance Data Mart API (GL, AR, AP, Cash, VAT)."""

from __future__ import annotations

import frappe
from frappe.utils import flt

from omnexa_accounting.utils.vat_accounts import resolve_vat_accounts
from omnexa_intelligence_core.api import get_finance_bi_dataset


def _ar_ap_summary(company: str, from_date: str, to_date: str) -> dict:
	ar = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(outstanding_amount), 0) AS outstanding, COUNT(*) AS open_count
		FROM `tabSales Invoice`
		WHERE company = %(company)s AND docstatus = 1 AND outstanding_amount > 0
		  AND posting_date <= %(to_date)s
		""",
		{"company": company, "to_date": to_date},
		as_dict=True,
	)[0]
	ap = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(outstanding_amount), 0) AS outstanding, COUNT(*) AS open_count
		FROM `tabPurchase Invoice`
		WHERE company = %(company)s AND docstatus = 1 AND outstanding_amount > 0
		  AND posting_date <= %(to_date)s
		""",
		{"company": company, "to_date": to_date},
		as_dict=True,
	)[0]
	return {
		"ar_outstanding": flt(ar.get("outstanding")),
		"ar_open_invoices": int(ar.get("open_count") or 0),
		"ap_outstanding": flt(ap.get("outstanding")),
		"ap_open_invoices": int(ap.get("open_count") or 0),
	}


def _cash_position(company: str, to_date: str) -> dict:
	bank_accounts = frappe.get_all(
		"Bank Account",
		filters={"company": company},
		fields=["name", "gl_account"],
	)
	total = 0.0
	for ba in bank_accounts:
		if not ba.gl_account:
			continue
		bal = frappe.db.sql(
			"""
			SELECT COALESCE(SUM(debit - credit), 0)
			FROM `tabGL Entry`
			WHERE company = %(company)s AND account = %(account)s
			  AND posting_date <= %(to_date)s AND is_cancelled = 0
			""",
			{"company": company, "account": ba.gl_account, "to_date": to_date},
		)[0][0]
		total += flt(bal)
	return {"cash_and_bank_balance": total, "bank_accounts": len(bank_accounts)}


def _vat_snapshot(company: str) -> dict:
	vat = resolve_vat_accounts(company)
	return {
		"input_vat_gl": vat.get("input_vat_gl"),
		"output_vat_gl": vat.get("output_vat_gl"),
		"input_source": vat.get("input_source"),
		"output_source": vat.get("output_source"),
	}


@frappe.whitelist(methods=["GET", "POST"])
def get_finance_data_mart(company: str, from_date: str, to_date: str) -> dict:
	"""Unified finance data mart for BI tools (Metabase / Superset / Power BI)."""
	if frappe.session.user == "Guest":
		frappe.throw("Login required.", frappe.PermissionError)

	base = get_finance_bi_dataset(company=company, from_date=from_date, to_date=to_date)
	return {
		"ok": True,
		"schema_version": "2026-06-25",
		"company": company,
		"period": {"from_date": from_date, "to_date": to_date},
		"gl": base.get("kpis") or {},
		"ar_ap": _ar_ap_summary(company, from_date, to_date),
		"cash": _cash_position(company, to_date),
		"vat": _vat_snapshot(company),
		"read_replica_hint": {
			"recommended": bool(frappe.conf.get("read_from_replica")),
			"site_config_key": "read_from_replica",
		},
	}
