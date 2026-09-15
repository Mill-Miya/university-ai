from __future__ import annotations

from university_ai.agent.models import AgentRequest, AgentResponse, Intent, ModelRoute, PolicyDecision, ToolCall


class AgentOrchestrator:
    """Coordinates existing services; it contains no database, RAG, or runtime implementation."""

    _TOOLS = {
        Intent.TASK_QUERY: "get_assignments",
        Intent.EXAM_QUERY: "get_exams",
        Intent.COURSE_QUERY: "get_schedule",
        Intent.SCHEDULE_QUERY: "get_schedule",
        Intent.DOCUMENT_SEARCH: "search_documents",
    }

    def __init__(self, intent_router, context_builder, policy_engine, model_router, tools, *, llm_service=None) -> None:
        self._intent_router, self._context_builder = intent_router, context_builder
        self._policy, self._model_router, self._tools, self._llm = policy_engine, model_router, tools, llm_service

    def handle(self, request: AgentRequest) -> AgentResponse:
        intent = self._intent_router.route(request)
        route = self._model_router.route(intent)
        tool_name = self._TOOLS.get(intent)
        if tool_name:
            arguments = {"question": request.text} if tool_name == "search_documents" else {}
            result, policy = self._tools.execute(ToolCall(tool_name, arguments))
            return AgentResponse(result.text, intent, route, policy, tool_name, result.metadata)
        context = self._context_builder.build(request, intent)
        if context.requires_abstention:
            return AgentResponse("取り込まれた資料から十分な根拠を見つけられませんでした。", intent, route,
                                 PolicyDecision.READ_ONLY, metadata={"context": context, "abstained": True})
        if route is ModelRoute.FAST and self._llm is not None:
            response = self._llm.ask(request.text + context.user_context_suffix(), system_prompt=context.system_prompt())
            return AgentResponse(response.text, intent, route, PolicyDecision.READ_ONLY, metadata={"model": response.model, "context": context})
        return AgentResponse("この要求は現在のAgent Phase 1では処理できません。", intent, route, PolicyDecision.DENIED, metadata={"context": context})
