from __future__ import annotations

from mooomoocatrag.models import ChatResponse

OFF_TOPIC_RESPONSE = "这个问题超出了猫笔刀文章库的范围，我只能回答与猫笔刀文章相关的问题。"


def handle_off_topic() -> ChatResponse:
    return ChatResponse(
        answer=OFF_TOPIC_RESPONSE,
        citations=[],
        retrieved_count=0,
        intent="off_topic",
    )
