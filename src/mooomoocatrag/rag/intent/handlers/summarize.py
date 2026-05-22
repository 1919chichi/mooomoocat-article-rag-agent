from __future__ import annotations

from openai import OpenAI

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChatResponse, IndexManifest
from mooomoocatrag.rag.prompt import format_citations
from mooomoocatrag.rag.retriever import retrieve

_SUMMARIZE_SYSTEM = """你是一个基于猫笔刀文章库做内容总结的 Agent。
请根据给定的文章片段，对用户请求的内容进行结构化总结。
使用 [1]、[2] 等标记引用对应片段。
如果文章片段不足以支撑总结，说明"当前猫笔刀文章库中没有找到足够依据"。"""

_NO_CONTENT = "当前猫笔刀文章库中没有找到足够依据。"


def handle_summarize(
    query: str,
    history: list[dict],
    config: Settings,
    manifest: IndexManifest,
) -> ChatResponse:
    results = retrieve(query, config, manifest)
    if not results:
        return ChatResponse(
            answer=_NO_CONTENT,
            citations=[],
            retrieved_count=0,
            intent="summarize",
        )

    context_parts = ["以下是检索到的文章片段：\n"]
    for i, result in enumerate(results, 1):
        context_parts.append(f"[{i}] {result.chunk.text}")
    context_parts.append(f"\n用户请求：{query}")

    messages: list[dict] = [
        {"role": "system", "content": _SUMMARIZE_SYSTEM},
        {"role": "user", "content": "\n".join(context_parts)},
    ]

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
