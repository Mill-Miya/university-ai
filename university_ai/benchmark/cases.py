from __future__ import annotations

import json
from pathlib import Path

from university_ai.benchmark.models import BenchmarkCase, EvaluationType


def load_cases(path: Path) -> list[BenchmarkCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("benchmark fixture must be a JSON array")
    cases: list[BenchmarkCase] = []
    ids: set[str] = set()
    for item in raw:
        required = {"id", "category", "input", "expected", "evaluation_type", "timeout"}
        if not required <= item.keys():
            raise ValueError("benchmark case is missing required fields")
        if item["id"] in ids:
            raise ValueError(f"duplicate benchmark case id: {item['id']}")
        ids.add(item["id"])
        cases.append(BenchmarkCase(
            id=str(item["id"]), category=str(item["category"]), input=str(item["input"]),
            expected=dict(item["expected"]), evaluation_type=EvaluationType(item["evaluation_type"]),
            timeout_seconds=float(item["timeout"]), target=str(item.get("target", "llm")),
            image_fixture=str(item["image_fixture"]) if item.get("image_fixture") else None,
        ))
    return cases
