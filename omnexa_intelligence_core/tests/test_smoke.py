from frappe.tests.utils import FrappeTestCase

from omnexa_intelligence_core import hooks


class TestIntelligenceCoreSmoke(FrappeTestCase):
	def test_hooks_are_present(self):
		self.assertEqual(hooks.app_name, "omnexa_intelligence_core")
		self.assertIn("omnexa_setup_intelligence", hooks.required_apps)

