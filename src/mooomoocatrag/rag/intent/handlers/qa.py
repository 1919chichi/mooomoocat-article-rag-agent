from __future__ import annotations

from openai import OpenAI

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChatResponse, IndexManifest
from mooomoocatrag.rag.prompt import (
    INSUFFICIENT_CONTENT_RESPONSE,
    SYSTEM_PROMPT,
    build_rag_prompt,
    format_citations,
)
from mooomoocatrag.rag.retriever import retrieve
from mooomoocatrag.utils import estimate_tokens

_VALID_HISTORY_ROLES = {"user", "assistant"}


def _recent_valid_history(history: list[dict], max_messages: int) -> list[dict]:
    valid = [
        {"role": turn.get("role", "user"), "content": turn.get("content", "")}
        for turn in history
        if turn.get("role", "user") in _VALID_HISTORY_ROLES
    ]
    return valid[-max_messages:] if max_messages > 0 else []


def handle_qa(
    query: str,
    history: list[dict],
    config: Settings,
    manifest: IndexManifest,
) -> ChatResponse:
    results = retrieve(query, config, manifest)
    if not results:
        return ChatResponse(
            answer=INSUFFICIENT_CONTENT_RESPONSE,
            citations=[],
            retrieved_count=0,
            intent="qa",
        )

    input_token_budget = config.LLM_CONTEXT_WINDOW - config.MAX_OUTPUT_TOKENS
    system_prompt_tokens = estimate_tokens(SYSTEM_PROMPT)

    max_history_messages = config.CHAT_HISTORY_TURNS * 2
    trimmed_history = _recent_valid_history(history, max_history_messages)
    adjusted_results = sorted(results, key=lambda r: r.similarity, reverse=True)

    retrieved_tokens = sum(estimate_tokens(r.chunk.text) for r in adjusted_results)
    query_tokens = estimate_tokens(query)
    history_tokens = sum(estimate_tokens(t.get("content", "")) for t in trimmed_history)
    total_estimated = system_prompt_tokens + retrieved_tokens + query_tokens + history_tokens

    if total_estimated > input_token_budget:
        for keep_count in range(len(adjusted_results), 0, -1):
            test_results = adjusted_results[:keep_count]
            test_tokens = sum(estimate_tokens(r.chunk.text) for r in test_results)
            test_total = system_prompt_tokens + test_tokens + query_tokens + history_tokens
            if test_total <= input_token_budget:
                adjusted_results = test_results
                break
        else:
            adjusted_results = adjusted_results[:1]

    messages = build_rag_prompt(query, adjusted_results, trimmed_history)
    client = OpenAI(
        base_url=config.effective_llm_base_url,
        api_key=config.effective_llm_api_key,
    )
    response = client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=messages,
        max_tokens=config.MAX_OUTPUT_TOKENS,
    )
    answer = response.choices[0].message.content or ""
    return ChatResponse(
        answer=answer,
        citations=format_citations(adjusted_results),
        retrieved_count=len(adjusted_results),
        intent="qa",
    )
