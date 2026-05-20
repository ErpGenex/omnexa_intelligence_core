# Copyright (c) 2026, ErpGenEx
from frappe.tests.utils import FrappeTestCase
from omnexa_core.omnexa_core.infra_parity import preview_infra

class TestSapParityInfraApp(FrappeTestCase):
	def test_infra_kpi(self):
		out = preview_infra("intelligence_core", active_signals=2, avg_confidence=0.8)
		self.assertEqual(out["vertical"], "intelligence_core")
