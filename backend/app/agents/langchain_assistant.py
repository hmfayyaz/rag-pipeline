import logging
from typing import Any, TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelRetryMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)
from langchain.tools import tool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph

from app.agents.prompts import get_system_prompt_with_rag
from app.agents.tools.rag_tool import _active_kb_collections, search_knowledge_base
from app.agents.utils import get_current_datetime
from app.core.config import settings

logger = logging.getLogger(__name__)


class AgentContext(TypedDict, total=False):
    """Runtime context passed to agent.invoke()/stream()."""

    user_id: str | None
    user_name: str | None
    # Resolved server-side from conversation.active_knowledge_base_ids — never from the LLM
    kb_collection_names: list[str]
    metadata: dict[str, Any]


@tool
def current_datetime() -> dict[str, str]:
    """Get the current date and time.

    Use this tool when you need to know the current date or time.
    """
    return get_current_datetime()


@tool
async def search_documents(query: str, top_k: int = 5) -> str:
    """Search the knowledge base for relevant documents.

    Use this tool to find information from uploaded documents before answering user queries.
    Searches across all knowledge bases active for this conversation.
    Cite sources by referring to the document filename from the search results.

    Args:
        query: The search query string.
        top_k: Number of top results to retrieve (default: 5).

    Returns:
        Formatted string with search results including content and scores.
    """
    return await search_knowledge_base(query=query, top_k=top_k)


class LangChainAssistant:
    def __init__(
        self,
        model_name: str | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
        thinking_effort: str | None = None,
    ):
        self.model_name = model_name or settings.AI_MODEL
        self.temperature = temperature or settings.AI_TEMPERATURE
        # Extended-thinking effort for reasoning-capable models. ``None`` keeps
        # the model in plain mode; "low"/"medium"/"high" enables provider-
        # specific reasoning (Claude extended thinking, OpenAI o-series, etc).
        self.thinking_effort = (
            thinking_effort
            if thinking_effort is not None
            else (settings.AI_THINKING_EFFORT if settings.AI_THINKING_ENABLED else None)
        )
        self.system_prompt = system_prompt or get_system_prompt_with_rag()
        self._agent: CompiledStateGraph | None = None
        self._tools = [current_datetime]
        self._tools.append(search_documents)

    def _create_agent(self) -> CompiledStateGraph:
        # OpenAI: ``reasoning`` is honored only by the Responses API.
        openai_kwargs: dict[str, Any] = {}
        if self.thinking_effort:
            openai_kwargs["reasoning"] = {
                "effort": self.thinking_effort,
                "summary": "auto",
            }
            openai_kwargs["use_responses_api"] = True
            openai_kwargs["output_version"] = "responses/v1"
        model = ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE or None,
            **openai_kwargs,
        )

        return create_agent(
            model=model,
            tools=self._tools,
            system_prompt=self.system_prompt,
            context_schema=AgentContext,
            middleware=[
                ModelRetryMiddleware(max_retries=2),
                ToolRetryMiddleware(max_retries=1),
                ToolCallLimitMiddleware(run_limit=15),
            ],
        )

    @property
    def agent(self) -> CompiledStateGraph:
        if self._agent is None:
            self._agent = self._create_agent()
        return self._agent

    @staticmethod
    def _convert_history(
        history: list[dict[str, str]] | None,
    ) -> list[HumanMessage | AIMessage | SystemMessage]:
        messages: list[HumanMessage | AIMessage | SystemMessage] = []

        for msg in history or []:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
            elif msg["role"] == "system":
                messages.append(SystemMessage(content=msg["content"]))

        return messages

    async def run(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        context: AgentContext | None = None,
    ) -> tuple[str, list[Any], AgentContext]:
        messages = self._convert_history(history)
        messages.append(HumanMessage(content=user_input))

        agent_context: AgentContext = context if context is not None else {}

        logger.info("Running agent with user input: %s...", user_input[:100])
        token = _active_kb_collections.set(agent_context.get("kb_collection_names") or [])
        try:
            result = await self.agent.ainvoke(
                {"messages": messages},
                config={"configurable": agent_context} if agent_context else None,
            )
        finally:
            _active_kb_collections.reset(token)

        output = ""
        tool_events: list[Any] = []

        for message in result.get("messages", []):
            if hasattr(message, "content") and isinstance(message, AIMessage):
                output = message.content
            if hasattr(message, "tool_calls") and message.tool_calls:
                tool_events.extend(message.tool_calls)

        logger.info("Agent run complete. Output length: %d chars", len(output))

        return output, tool_events, agent_context

    async def stream(
        self,
        user_input: str,
        history: list[dict[str, str]] | None = None,
        context: AgentContext | None = None,
    ):
        messages = self._convert_history(history)
        messages.append(HumanMessage(content=user_input))

        agent_context: AgentContext = context if context is not None else {}
        token = _active_kb_collections.set(agent_context.get("kb_collection_names") or [])
        try:
            async for event in self.agent.astream(
                {"messages": messages},
                stream_mode=["messages", "updates"],
                config={"configurable": agent_context} if agent_context else None,
            ):
                yield event
        finally:
            _active_kb_collections.reset(token)


def get_agent(
    model_name: str | None = None,
    thinking_effort: str | None = None,
) -> LangChainAssistant:
    return LangChainAssistant(model_name=model_name, thinking_effort=thinking_effort)


async def run_agent(
    user_input: str,
    history: list[dict[str, str]],
    context: AgentContext | None = None,
) -> tuple[str, list[Any], AgentContext]:
    agent = get_agent()
    return await agent.run(user_input, history, context)
