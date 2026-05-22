from __future__ import annotations

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChatResponse, IndexManifest
from mooomoocatrag.rag.intent import IntentRouter, IntentType
from mooomoocatrag.rag.intent.handlers import (
    INSUFFICIENT_CONTENT_RESPONSE,
    handle_chitchat,
    handle_list,
    handle_off_topic,
    handle_qa,
    handle_summarize,
)

# Backward-compatible alias kept for existing imports.
NO_INSUFFICIENT_CONTENTResponse = INSUFFICIENT_CONTENT_RESPONSE


def chat_turn(
    query: str,
    history: list[dict],
    config: Settings,
    manifest: IndexManifest,
) -> ChatResponse:
    """Route a single conversation turn to the appropriate handler based on intent."""
    router = IntentRouter(config)
    intent_result = router.classify(query, history)

    if intent_result.intent == IntentType.CHITCHAT:
        return handle_chitchat(query, history, config)
    if intent_result.intent == IntentType.OFF_TOPIC:
        return handle_off_topic()
    if intent_result.intent == IntentType.LIST:
        return handle_list(query, manifest)
    if intent_result.intent == IntentType.SUMMARIZE:
        return handle_summarize(query, history, config, manifest)
    return handle_qa(query, history, config, manifest)
