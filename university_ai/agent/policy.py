from __future__ import annotations

from university_ai.agent.models import PolicyDecision, ToolCall


class PolicyEngine:
    """Central allow-list policy. Tool execution never bypasses this boundary."""

    _READ_ONLY = frozenset({"get_schedule", "get_assignments", "get_exams", "search_documents"})
    _SAFE_ACTION = frozenset({"show_notification"})
    _CONFIRM_REQUIRED = frozenset({"open_application", "open_file", "write_document", "execute_command"})

    def evaluate(self, call: ToolCall) -> PolicyDecision:
        if call.name in self._READ_ONLY:
            return PolicyDecision.READ_ONLY
        if call.name in self._SAFE_ACTION:
            return PolicyDecision.SAFE_ACTION
        if call.name in self._CONFIRM_REQUIRED:
            return PolicyDecision.CONFIRM_REQUIRED
        return PolicyDecision.DENIED

    @staticmethod
    def permits(decision: PolicyDecision) -> bool:
        return decision in {PolicyDecision.READ_ONLY, PolicyDecision.SAFE_ACTION}
