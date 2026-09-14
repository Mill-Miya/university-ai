from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from university_ai.benchmark.cases import load_cases
from university_ai.benchmark.evaluate import evaluate
from university_ai.benchmark.models import BenchmarkCase, BenchmarkStatus, EvaluationType
from university_ai.benchmark.report import summarize, write_reports
from university_ai.benchmark.runner import BenchmarkRunner
from university_ai.llm.config import ModelBackendConfig
from university_ai.llm.models import LlmResponse


class FakeBackend:
    def __init__(self, available=True, output="日本語の回答", delay=0):
        self.available, self.output, self.delay = available, output, delay
    def availability(self): return self.available
    def model_info(self): return {"runtime": "fake", "model": "fake-model"}
    def generate(self, _request):
        if self.delay: time.sleep(self.delay)
        return LlmResponse(self.output, "fake-model", "fake", datetime.now(UTC), self.delay,
                           {"load_duration_ns": 10, "prompt_eval_duration_ns": 20, "eval_duration_ns": 1_000_000_000,
                            "eval_count": 12, "tokens_per_second": 12.0})
    def shutdown(self): pass


def case(evaluation_type=EvaluationType.CONTAINS, *, timeout=1, target="llm", expected=None):
    return BenchmarkCase("case", "test", "input", expected or {"contains": ["回答"]}, evaluation_type, timeout, target)


def test_external_case_fixture_loads_initial_matrix():
    cases = load_cases(__import__("pathlib").Path("university_ai/benchmark/fixtures/fast_brain_cases.json"))
    assert len(cases) == 30 and {item.category for item in cases} >= {"RAG", "Latency", "Intent classification"}
    assert all(item.timeout_seconds > 0 for item in cases)


def test_evaluator_supports_automatic_and_manual_categories():
    assert evaluate(case(), "回答")[0] is True
    assert evaluate(case(EvaluationType.JSON, expected={"required_keys": ["status"]}), '{"status":"ok"}')[0] is True
    assert evaluate(case(EvaluationType.NO_THINKING, expected={}), "<think>bad</think>")[0] is False
    assert evaluate(case(EvaluationType.MANUAL, expected={}), "anything")[0] is None
    assert evaluate(case(EvaluationType.INTENT, expected={"intent": "TASK_QUERY"}), "", intent="TASK_QUERY")[0] is True


def test_runner_collects_backend_metrics_and_timeout_without_real_model():
    config = ModelBackendConfig(model="fake-model")
    result = BenchmarkRunner(FakeBackend(), config=config).run_case(case())
    assert result.status is BenchmarkStatus.PASSED and result.tokens_per_second == 12.0 and result.ttft_seconds == 30 / 1e9
    timed_out = BenchmarkRunner(FakeBackend(delay=.02), config=config).run_case(case(timeout=.001))
    assert timed_out.status is BenchmarkStatus.TIMEOUT


def test_runner_skips_unavailable_or_uninjected_targets():
    config = ModelBackendConfig(model="not-installed")
    skipped = BenchmarkRunner(FakeBackend(False), config=config).run_case(case(), backend_available=False)
    assert skipped.status is BenchmarkStatus.SKIPPED
    agent_case = case(EvaluationType.INTENT, target="agent", expected={"intent": "TASK_QUERY"})
    assert BenchmarkRunner(FakeBackend(), config=config).run_case(agent_case).status is BenchmarkStatus.SKIPPED


def test_result_json_and_markdown_reporting(tmp_path):
    config = ModelBackendConfig(model="fake-model")
    results = [BenchmarkRunner(FakeBackend(), config=config).run_case(case())]
    json_path, markdown_path = write_reports(tmp_path, results, {"runtime": "fake", "model": "fake-model"})
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["success_rate"] == 1 and markdown_path.read_text(encoding="utf-8").startswith("# N.O.V.A.")
    assert summarize(results)["average_tokens_per_second"] == 12.0
