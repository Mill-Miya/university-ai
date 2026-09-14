from __future__ import annotations

import json
import re

from university_ai.benchmark.models import BenchmarkCase


def evaluate(case: BenchmarkCase, output: str, *, intent: str | None = None, tool_name: str | None = None) -> tuple[bool | None, str | None]:
    """Return None when judgment is intentionally reserved for human review."""
    expected = case.expected
    if case.evaluation_type.value == "manual":
        return None, "manual review required"
    if case.evaluation_type.value == "contains":
        terms = expected.get("contains", [])
        return all(term.lower() in output.lower() for term in terms), None
    if case.evaluation_type.value == "japanese":
        return bool(re.search(r"[\u3040-\u30ff\u3400-\u9fff]", output)), None
    if case.evaluation_type.value == "no_thinking":
        return "<think>" not in output.lower() and not bool(expected.get("forbidden") and any(item in output for item in expected["forbidden"])), None
    if case.evaluation_type.value == "json":
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            return False, "invalid JSON"
        required = expected.get("required_keys", [])
        return isinstance(parsed, dict) and all(key in parsed for key in required), None
    if case.evaluation_type.value == "intent":
        return intent == expected.get("intent"), None
    if case.evaluation_type.value == "tool":
        return tool_name == expected.get("tool"), None
    return False, "unsupported evaluation type"
