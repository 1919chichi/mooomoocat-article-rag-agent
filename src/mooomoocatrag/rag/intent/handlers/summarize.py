from __future__ import annotations

from openai import OpenAI

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChatResponse, IndexManifest
from mooomoocatrag.rag.prompt import (
    INSUFFICIENT_CONTENT_RESPONSE,
    build_summarize_prompt,
    format_citations,
)
from mooomoocatrag.rag.retriever import retrieve


def handle_summarize(
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
            intent="summarize",
        )

    messages = build_summarize_prompt(query, results)

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
        citations=format_citations(results),
        retrieved_count=len(results),
        intent="summarize",
    )
