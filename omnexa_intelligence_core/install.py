from __future__ import annotations

from omnexa_intelligence_core.engine.analyzers import run_core_analyzers


def after_install():
	run_core_analyzers()


def after_migrate():
	run_core_analyzers()

