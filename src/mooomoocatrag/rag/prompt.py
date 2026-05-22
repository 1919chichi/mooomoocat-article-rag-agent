from __future__ import annotations

from mooomoocatrag.models import RetrievalResult

INSUFFICIENT_CONTENT_RESPONSE = "当前猫笔刀文章库中没有找到足够依据。"

SYSTEM_PROMPT = """你是一个基于猫笔刀文章库回答问题的 Agent。
你必须优先依据给定的文章片段回答。
使用 [1]、[2] 等标记引用对应片段。
不要把没有出现在文章片段中的内容说成猫笔刀文章观点。
如果文章片段不足以回答，直接说明"当前猫笔刀文章库中没有找到足够依据"。"""

SUMMARIZE_SYSTEM_PROMPT = """你是一个基于猫笔刀文章库做内容总结的 Agent。
请根据给定的文章片段，对用户请求的内容进行结构化总结。
使用 [1]、[2] 等标记引用对应片段。
如果文章片段不足以支撑总结，说明"当前猫笔刀文章库中没有找到足够依据"。"""


def build_rag_prompt(
    query: str, results: list[RetrievalResult], history: list[dict] | None = None
) -> list[dict]:
    """构造 OpenAI Chat Completions 格式的 RAG prompt，包含 system 指令、检索片段和对话历史。"""
    messages: list[dict] = []
    messages.append({"role": "system", "content": SYSTEM_PROMPT})

    if results:
        context_parts = ["以下是检索到的文章片段：\n"]
        for i, result in enumerate(results, 1):
            context_parts.append(f"[{i}] {result.chunk.text}")
        context_parts.append("")
        context_parts.append(f"用户问题：{query}")
        context = "\n".join(context_parts)
    else:
        context = f"用户问题：{query}\n\n当前猫笔刀文章库中没有找到足够依据。"

    if history:
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": context})
    return messages


def build_summarize_prompt(query: str, results: list[RetrievalResult]) -> list[dict]:
    context_parts = ["以下是检索到的文章片段：\n"]
    for i, result in enumerate(results, 1):
        context_parts.append(f"[{i}] {result.chunk.text}")
    context_parts.append(f"\n用户请求：{query}")
    return [
        {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(context_parts)},
    ]


def format_citations(results: list[RetrievalResult]) -> list[str]:
    """由程序生成引用列表，不依赖 LLM，避免 LLM 伪造或遗漏引用。"""
    citations: list[str] = []
    for i, result in enumerate(results, 1):
        heading = result.chunk.nearest_heading
        heading_part = f"小标题：{heading}" if heading else "小标题：无"
        citation = (
            f"[{i}] {result.chunk.title} | {result.chunk.source_rel_path} | "
            f"chunk {result.chunk.chunk_index} | {heading_part}"
        )
        citations.append(citation)
    return citations
