from __future__ import annotations

"""Explicit local-only Vision benchmark runner.

It deliberately never downloads models or fixture images. Supply an image root
containing the named fixtures when running a real hardware comparison.
"""

import argparse
import time
from pathlib import Path

from university_ai.benchmark.cases import load_cases
from university_ai.benchmark.evaluate import evaluate
from university_ai.benchmark.models import BenchmarkResult, BenchmarkStatus
from university_ai.benchmark.report import write_reports
from university_ai.llm.config import ModelBackendConfig
from university_ai.llm.factory import create_model_backend
from university_ai.llm.models import ImageInput
from university_ai.llm.service import LlmService


def run_vision_cases(cases, service: LlmService, image_root: Path) -> list[BenchmarkResult]:
    results = []
    for case in cases:
        path = image_root / (case.image_fixture or "")
        if not case.image_fixture or not path.is_file():
            results.append(BenchmarkResult(case.id, case.category, BenchmarkStatus.SKIPPED, reason="vision fixture image unavailable"))
            continue
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        started = time.monotonic()
        try:
            response = service.ask_multimodal(case.input, (ImageInput(path.read_bytes(), mime),))
            passed, reason = evaluate(case, response.text)
            status = BenchmarkStatus.MANUAL_REVIEW if passed is None else BenchmarkStatus.PASSED if passed else BenchmarkStatus.FAILED
            results.append(BenchmarkResult(case.id, case.category, status, response.text, reason,
                time.monotonic() - started, model=response.model, runtime=response.runtime, metadata=dict(response.metadata)))
        except Exception as error:
            results.append(BenchmarkResult(case.id, case.category, BenchmarkStatus.ERROR, reason=type(error).__name__, total_latency_seconds=time.monotonic()-started))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run explicit local N.O.V.A. vision benchmark")
    parser.add_argument("--cases", type=Path, default=Path(__file__).parent / "fixtures" / "vision_cases.json")
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path.cwd() / "benchmark-results" / "vision")
    parser.add_argument("--runtime", default="ollama")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434")
    args = parser.parse_args(argv)
    config = ModelBackendConfig(runtime=args.runtime, model=args.model, endpoint=args.endpoint)
    backend = create_model_backend(config)
    results = run_vision_cases(load_cases(args.cases), LlmService(backend, config), args.image_root)
    json_path, markdown_path = write_reports(args.output_dir, results, backend.model_info())
    print(f"JSON: {json_path}\nMarkdown: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
