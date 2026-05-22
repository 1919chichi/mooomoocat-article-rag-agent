from __future__ import annotations

from openai import OpenAI

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChatResponse

_CHITCHAT_SYSTEM = (
    "你是猫笔刀文章 Agent 的助手。"
    "请简短友好地回复用户的闲聊，并适时引导用户提问与猫笔刀文章相关的问题。"
    "回复控制在 50 字以内。"
)


def handle_chitchat(
    query: str,
    history: list[dict],
    config: Settings,
) -> ChatResponse:
    client = OpenAI(
        base_url=config.effective_llm_base_url,
        api_key=config.effective_llm_api_key,
    )
    messages: list[dict] = [{"role": "system", "content": _CHITCHAT_SYSTEM}]
    if history:
        messages.extend(history[-4:])
    messages.append({"role": "user", "content": query})

    response = client.chat.completions.create(
        model=config.effective_intent_llm_model,
        messages=messages,
        max_tokens=128,
        temperature=0.7,
    )
    answer = response.choices[0].message.content or ""
    return ChatResponse(
        answer=answer,
        citations=[],
        retrieved_count=0,
        intent="chitchat",
    )
