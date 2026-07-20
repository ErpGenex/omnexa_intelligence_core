from __future__ import annotations

import frappe

from omnexa_intelligence_core.engine.analyzers import run_core_analyzers


SUPPORTED_FRAPPE_MAJOR = 15


def enforce_supported_frappe_version():
	"""Fail early when running on an unsupported Frappe major release."""
	version_text = (getattr(frappe, "__version__", "") or "").strip()
	if not version_text:
		return

	major_token = version_text.split(".", 1)[0]
	try:
		major = int(major_token)
	except ValueError:
		return

	if major != SUPPORTED_FRAPPE_MAJOR:
		frappe.throw(
			f"Unsupported Frappe version '{version_text}' for omnexa_intelligence_core. "
			"Supported range is >=15.0,<16.0.",
			frappe.ValidationError,
		)


def after_install():
	_safe_run_core_analyzers()


def after_migrate():
	_safe_run_core_analyzers()


def _safe_run_core_analyzers():
	"""Keep fresh-install flow resilient when dependent doctypes are not ready yet."""
	try:
		run_core_analyzers()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Intelligence Core: run_core_analyzers during install/migrate")

