# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from omnexa_intelligence_core.finance_ai import ask_finance_assistant, predict_finance_metrics
from omnexa_intelligence_core.finance_data_mart import get_finance_data_mart


class TestFinanceDataMart(FrappeTestCase):
	def setUp(self):
		from omnexa_core.tests.test_helpers import clear_privileged_view_context

		clear_privileged_view_context()
		self.company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		if not self.company:
			self.skipTest("No company on site")
		self.to_date = today()
		self.from_date = add_days(self.to_date, -30)

	def test_guest_cannot_access_data_mart(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_finance_data_mart(self.company, self.from_date, self.to_date)

	def test_admin_can_access_data_mart(self):
		frappe.set_user("Administrator")
		result = get_finance_data_mart(self.company, self.from_date, self.to_date)
		self.assertTrue(result.get("ok"))
		self.assertEqual(result.get("company"), self.company)


class TestFinanceAI(FrappeTestCase):
	def setUp(self):
		from omnexa_core.tests.test_helpers import clear_privileged_view_context

		clear_privileged_view_context()
		self.company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		if not self.company:
			self.skipTest("No company on site")

	def test_guest_cannot_use_finance_assistant(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			ask_finance_assistant(self.company, "What is revenue?")

	def test_predict_finance_metrics_for_admin(self):
		frappe.set_user("Administrator")
		result = predict_finance_metrics(self.company)
		self.assertTrue(result.get("ok"))
		self.assertGreaterEqual(len(result.get("predictions") or []), 1)

	def test_ask_finance_assistant_for_admin(self):
		frappe.set_user("Administrator")
		result = ask_finance_assistant(self.company, "What is revenue?")
		self.assertTrue(result.get("ok"))
		self.assertTrue(result.get("answer"))
		self.assertEqual(result.get("source"), "finance_data_mart")
