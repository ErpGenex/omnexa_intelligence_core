from __future__ import annotations

from omnexa_intelligence_core.engine.analyzers import run_core_analyzers
from omnexa_intelligence_core.api import enqueue_playbook_actions, execute_pending_actions


def hourly_long():
	run_core_analyzers()
	enqueue_playbook_actions(auto_approve=1)
	execute_pending_actions(dry_run=1, limit=25)

