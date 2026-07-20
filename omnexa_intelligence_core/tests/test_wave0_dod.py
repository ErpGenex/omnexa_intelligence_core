# Copyright (c) 2026, Omnexa and contributors
# License: MIT. See license.txt

"""Wave 0 Definition-of-Done smoke — omnexa_intelligence_core."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from omnexa_intelligence_core.finance_ai import ask_finance_assistant, predict_finance_metrics
from omnexa_intelligence_core.finance_data_mart import get_finance_data_mart
from omnexa_core.tests.test_helpers import clear_privileged_view_context


class TestWave0DoDIntelligence(FrappeTestCase):
	def setUp(self):
		super().setUp()
		clear_privileged_view_context()
		self.company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		if not self.company:
			self.skipTest("No company")

	def test_finance_data_mart_e2e(self):
		frappe.set_user("Administrator")
		result = get_finance_data_mart(self.company, add_days(today(), -30), today())
		self.assertTrue(result.get("ok"))
		self.assertIn("gl", result)

	def test_finance_assistant_e2e(self):
		frappe.set_user("Administrator")
		result = ask_finance_assistant(self.company, "cash balance")
		self.assertTrue(result.get("ok"))
		self.assertIn("safety", result)

	def test_predictions_e2e(self):
		frappe.set_user("Administrator")
		result = predict_finance_metrics(self.company)
		self.assertTrue(result.get("ok"))
		self.assertGreaterEqual(len(result.get("predictions") or []), 2)
