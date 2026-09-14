from __future__ import annotations

from datetime import UTC, datetime

import pytest

from university_ai.agent.context_builder import ContextBuilder
from university_ai.agent.model_router import ModelRouter
from university_ai.agent.models import AgentRequest, Intent, ModelRoute, PolicyDecision, ToolCall, ToolResult
from university_ai.agent.orchestrator import AgentOrchestrator
from university_ai.agent.policy import PolicyEngine
from university_ai.agent.router import IntentRouter
from university_ai.agent.tools.academic import academic_tools
from university_ai.agent.tools.documents import document_tools
from university_ai.agent.tools.registry import Tool, ToolDeniedError, ToolRegistry, ToolValidationError
from university_ai.llm.models import LlmResponse


class FakeContextEngine:
    def __init__(self): self.calls = []
    def build(self, now): self.calls.append(now); return {"now": now}


class FakePresenter:
    def today_courses(self): return ["10:00 制御工学"]
    def assignments(self): return ["制御工学 | Report | 2026-09-30"]
    def exams(self): return ["制御工学 | Midterm"]


class FakeRag:
    def __init__(self): self.questions = []
    def answer(self, question):
        self.questions.append(question)
        return type("Rag", (), {"answer": "資料に基づく回答", "sources": ("source",), "abstained": False, "model": "fake"})()


class FakeLlm:
    def __init__(self): self.prompts = []
    def ask(self, prompt):
        self.prompts.append(prompt)
        return LlmResponse("会話回答", "fake-local", "fake", datetime.now(UTC), .01)


def make_orchestrator():
    context = FakeContextEngine(); policy = PolicyEngine(); registry = ToolRegistry(policy)
    for tool in academic_tools(FakePresenter()) + document_tools(FakeRag()): registry.register(tool)
    return AgentOrchestrator(IntentRouter(), ContextBuilder(context), policy, ModelRouter(), registry, llm_service=FakeLlm()), context


def request(text, explicit_intent=None):
    return AgentRequest(text, datetime.now(UTC), explicit_intent=explicit_intent)


def test_router_is_deterministic_and_explicit_intent_wins():
    router = IntentRouter()
    assert router.route(request("明日の課題は？")) is Intent.TASK_QUERY
    assert router.route(request("次の試験は？")) is Intent.EXAM_QUERY
    assert router.route(request("資料について質問")) is Intent.DOCUMENT_SEARCH
    assert router.route(request("雑談", Intent.SCHEDULE_QUERY)) is Intent.SCHEDULE_QUERY


def test_model_router_expresses_future_routes_without_switching_backends():
    router = ModelRouter()
    assert router.route(Intent.TASK_QUERY) is ModelRoute.RULE_ONLY
    assert router.route(Intent.DOCUMENT_SEARCH) is ModelRoute.FAST
    assert router.route(Intent.SCREEN_EXPLAIN) is ModelRoute.FAST_VISION
    assert router.route(Intent.CHAT) is ModelRoute.FAST


def test_policy_and_registry_validate_tool_existence_arguments_and_permission():
    policy = PolicyEngine(); registry = ToolRegistry(policy)
    registry.register(Tool("search_documents", "search", frozenset({"question"}), lambda args: ToolResult(args["question"])))
    result, decision = registry.execute(ToolCall("search_documents", {"question": "資料"}))
    assert result.text == "資料" and decision is PolicyDecision.READ_ONLY
    with pytest.raises(ToolValidationError): registry.execute(ToolCall("search_documents"))
    with pytest.raises(ToolValidationError): registry.execute(ToolCall("unknown"))
    registry.register(Tool("open_application", "open", frozenset(), lambda _args: ToolResult("opened")))
    with pytest.raises(ToolDeniedError): registry.execute(ToolCall("open_application"))


def test_orchestrator_prefers_existing_deterministic_academic_tool_over_llm():
    orchestrator, context = make_orchestrator()
    response = orchestrator.handle(request("明日の課題なんかあった？"))
    assert response.intent is Intent.TASK_QUERY and response.route is ModelRoute.RULE_ONLY
    assert response.policy is PolicyDecision.READ_ONLY and response.tool_name == "get_assignments"
    assert "Report" in response.text and len(context.calls) == 1


def test_orchestrator_delegates_document_questions_to_existing_rag_service():
    orchestrator, _context = make_orchestrator()
    response = orchestrator.handle(request("資料と課題の提出期限を教えて"))
    assert response.intent is Intent.TASK_QUERY  # explicit academic task keyword wins over document wording
    explicit = orchestrator.handle(request("資料を検索", Intent.DOCUMENT_SEARCH))
    assert explicit.tool_name == "search_documents" and explicit.text == "資料に基づく回答"
    assert explicit.metadata["sources"] == ("source",)


def test_orchestrator_uses_llm_only_for_non_tool_chat():
    orchestrator, _context = make_orchestrator()
    response = orchestrator.handle(request("こんにちは"))
    assert response.intent is Intent.CHAT and response.route is ModelRoute.FAST
    assert response.text == "会話回答" and response.tool_name is None
