from __future__ import annotations

import json
import statistics
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from university_ai.benchmark.models import BenchmarkResult, BenchmarkStatus


def summarize(results: list[BenchmarkResult]) -> dict:
    completed = [item for item in results if item.status not in {BenchmarkStatus.SKIPPED, BenchmarkStatus.MANUAL_REVIEW}]
    passed = [item for item in results if item.status is BenchmarkStatus.PASSED]
    latencies = [item.total_latency_seconds for item in completed if item.total_latency_seconds is not None]
    speeds = [item.tokens_per_second for item in completed if item.tokens_per_second is not None]
    categories: dict[str, dict] = defaultdict(lambda: {"total": 0, "passed": 0, "statuses": defaultdict(int)})
    for item in results:
        category = categories[item.category]; category["total"] += 1; category["statuses"][item.status.value] += 1
        if item.status is BenchmarkStatus.PASSED: category["passed"] += 1
    return {
        "total": len(results), "completed": len(completed), "passed": len(passed),
        "success_rate": len(passed) / len(completed) if completed else None,
        "average_latency_seconds": statistics.mean(latencies) if latencies else None,
        "median_latency_seconds": statistics.median(latencies) if latencies else None,
        "average_tokens_per_second": statistics.mean(speeds) if speeds else None,
        "categories": {name: {**value, "statuses": dict(value["statuses"])} for name, value in categories.items()},
    }


def write_reports(output_directory: Path, results: list[BenchmarkResult], backend_info: dict) -> tuple[Path, Path]:
    output_directory.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now(UTC).isoformat(), "backend": backend_info, "summary": summarize(results),
               "results": [item.to_dict() for item in results]}
    json_path = output_directory / "benchmark-results.json"
    markdown_path = output_directory / "benchmark-summary.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = payload["summary"]
    markdown_path.write_text(
        "# N.O.V.A. Fast Brain Benchmark\n\n"
        f"- Runtime: {backend_info.get('runtime', '-') }\n- Model: {backend_info.get('model', '-')}\n"
        f"- Total: {summary['total']} / Passed: {summary['passed']} / Success rate: {summary['success_rate']}\n"
        f"- Average latency: {summary['average_latency_seconds']} s\n- Median latency: {summary['median_latency_seconds']} s\n"
        f"- Average tokens/s: {summary['average_tokens_per_second']}\n\n"
        "| Category | Total | Passed | Statuses |\n|---|---:|---:|---|\n" + "\n".join(
            f"| {name} | {item['total']} | {item['passed']} | {item['statuses']} |" for name, item in summary["categories"].items()
        ) + "\n", encoding="utf-8")
    return json_path, markdown_path
