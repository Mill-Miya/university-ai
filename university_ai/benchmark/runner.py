from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime
from pathlib import Path

from university_ai.agent.models import AgentRequest
from university_ai.benchmark.cases import load_cases
from university_ai.benchmark.evaluate import evaluate
from university_ai.benchmark.models import BenchmarkCase, BenchmarkResult, BenchmarkStatus
from university_ai.benchmark.report import write_reports
from university_ai.llm.config import ModelBackendConfig
from university_ai.llm.factory import create_model_backend
from university_ai.llm.service import LlmService


class BenchmarkRunner:
    def __init__(self, backend, *, config: ModelBackendConfig, agent=None) -> None:
        self._backend, self._config, self._agent = backend, config, agent
        self._llm = LlmService(backend, config)

    def run(self, cases: list[BenchmarkCase]) -> list[BenchmarkResult]:
        available = self._backend.availability()
        return [self.run_case(case, backend_available=available) for case in cases]

    def run_case(self, case: BenchmarkCase, *, backend_available: bool | None = None) -> BenchmarkResult:
        if case.target == "agent":
            return self._run_agent(case)
        if backend_available is False or not self._backend.availability():
            return BenchmarkResult(case.id, case.category, BenchmarkStatus.SKIPPED, reason="backend or model unavailable",
                                   model=self._config.model, runtime=self._config.runtime)
        started = time.monotonic()
        try:
            response = self._llm.ask(case.input)
        except Exception as error:
            return BenchmarkResult(case.id, case.category, BenchmarkStatus.ERROR, reason=type(error).__name__,
                                   total_latency_seconds=time.monotonic() - started, model=self._config.model, runtime=self._config.runtime)
        elapsed = time.monotonic() - started
        metadata = response.metadata
        if elapsed > case.timeout_seconds:
            return BenchmarkResult(case.id, case.category, BenchmarkStatus.TIMEOUT, response.text, "timeout exceeded", elapsed,
                                   self._ttft(metadata), self._seconds(metadata.get("eval_duration_ns")), metadata.get("tokens_per_second"),
                                   metadata.get("prompt_eval_count"), metadata.get("eval_count"), response.model, response.runtime,
                                   None, dict(metadata))
        passed, reason = evaluate(case, response.text)
        status = BenchmarkStatus.MANUAL_REVIEW if passed is None else BenchmarkStatus.PASSED if passed else BenchmarkStatus.FAILED
        return BenchmarkResult(case.id, case.category, status, response.text, reason, elapsed, self._ttft(metadata),
                               self._seconds(metadata.get("eval_duration_ns")), metadata.get("tokens_per_second"),
                               metadata.get("prompt_eval_count"), metadata.get("eval_count"), response.model, response.runtime,
                               None, dict(metadata))

    def _run_agent(self, case: BenchmarkCase) -> BenchmarkResult:
        if self._agent is None:
            return BenchmarkResult(case.id, case.category, BenchmarkStatus.SKIPPED, reason="agent not supplied")
        started = time.monotonic()
        try:
            response = self._agent.handle(AgentRequest(case.input, datetime.now(UTC)))
            passed, reason = evaluate(case, response.text, intent=response.intent.value, tool_name=response.tool_name)
            status = BenchmarkStatus.MANUAL_REVIEW if passed is None else BenchmarkStatus.PASSED if passed else BenchmarkStatus.FAILED
            return BenchmarkResult(case.id, case.category, status, response.text, reason, time.monotonic() - started,
                                   model=response.metadata.get("model"), metadata={"intent": response.intent.value, "tool": response.tool_name})
        except Exception as error:
            return BenchmarkResult(case.id, case.category, BenchmarkStatus.ERROR, reason=type(error).__name__, total_latency_seconds=time.monotonic() - started)

    @staticmethod
    def _seconds(value) -> float | None:
        return float(value) / 1e9 if value else None

    @staticmethod
    def _ttft(metadata: dict) -> float | None:
        return BenchmarkRunner._seconds(metadata.get("load_duration_ns", 0) + metadata.get("prompt_eval_duration_ns", 0))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run explicit local N.O.V.A. Fast Brain benchmarks")
    parser.add_argument("--cases", type=Path, default=Path(__file__).parent / "fixtures" / "fast_brain_cases.json")
    parser.add_argument("--output-dir", type=Path, default=Path.cwd() / "benchmark-results")
    parser.add_argument("--runtime", default="ollama")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--case-id", action="append", default=[], help="Run only one or more fixture case IDs")
    args = parser.parse_args(argv)
    config = ModelBackendConfig(runtime=args.runtime, model=args.model, endpoint=args.endpoint, timeout_seconds=args.timeout)
    backend = create_model_backend(config)
    cases = load_cases(args.cases)
    if args.case_id:
        wanted = set(args.case_id)
        cases = [case for case in cases if case.id in wanted]
        missing = wanted - {case.id for case in cases}
        if missing:
            parser.error(f"unknown case IDs: {', '.join(sorted(missing))}")
    results = BenchmarkRunner(backend, config=config).run(cases)
    json_path, markdown_path = write_reports(args.output_dir, results, backend.model_info())
    print(f"JSON: {json_path}\nMarkdown: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
