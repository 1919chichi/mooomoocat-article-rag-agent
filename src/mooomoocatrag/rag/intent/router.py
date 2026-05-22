from __future__ import annotations

import logging
import re
import unicodedata
from typing import TYPE_CHECKING

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from mooomoocatrag.config import Settings
from mooomoocatrag.rag.intent.types import IntentResult, IntentType

logger = logging.getLogger(__name__)

# ── Chitchat whitelist ────────────────────────────────────────────────────────
_CHITCHAT_WHITELIST: frozenset[str] = frozenset({
    "你好", "您好", "早", "早安", "早上好", "晚安", "晚好",
    "谢谢", "谢了", "多谢", "感谢", "感谢你", "感谢您",
    "再见", "拜拜", "bye", "哈哈", "嗯嗯", "好的", "好",
    "哦", "嗯", "哦哦", "呵呵",
})

# ── Regex patterns ────────────────────────────────────────────────────────────
_LIST_PATTERN = re.compile(
    r"^(列举|列出|有哪些|哪些|所有).*(文章|文|讲|关于|介绍)"
)
_SUMMARIZE_PATTERN = re.compile(r"^(总结|摘要|概括|归纳)")


def _normalize(text: str) -> str:
    """Full-width → half-width, strip whitespace."""
    return unicodedata.normalize("NFKC", text).strip()


class RuleClassifier:
    """Zero-cost, conservative rule-based classifier.

    Returns None when no rule matches — the caller falls through to LLMClassifier.
    Intentionally has no OFF_TOPIC rule: off-topic detection requires semantic
    understanding and must go through the LLM.
    """

    def classify(self, query: str) -> IntentResult | None:
        q = _normalize(query)

        if len(q) <= 10 and q in _CHITCHAT_WHITELIST:
            return IntentResult(
                intent=IntentType.CHITCHAT,
                confidence=0.95,
                method="rule",
                metadata={"rule_id": "chitchat_greeting"},
            )

        if _LIST_PATTERN.search(q):
            return IntentResult(
                intent=IntentType.LIST,
                confidence=0.9,
                method="rule",
                metadata={"rule_id": "list_articles"},
            )

        if _SUMMARIZE_PATTERN.match(q):
            return IntentResult(
                intent=IntentType.SUMMARIZE,
                confidence=0.9,
                method="rule",
                metadata={"rule_id": "summarize_articles"},
            )

        return None


_INTENT_SYSTEM_PROMPT = """你是一个意图分类器，将用户的 query 分类为以下 5 类之一：

- chitchat：日常闲聊、问好、感谢、寒暄。例："你好"、"谢谢你"、"再见"
  反例："你好，帮我找一篇关于投资的文章"（有具体需求，应归为 qa 或 list）
- off_topic：与猫笔刀文章库完全无关的问题。例："帮我写一首诗"、"今天天气怎么样"
  反例："猫笔刀有没有写过理财的文章"（与文章库相关）
- list：要求列举文章。例："有哪些关于理财的文章"、"列出所有讲投资的文章"
- summarize：要求总结文章内容。例："总结一下猫笔刀关于消费观的文章"
- qa：普通问答，询问文章库中的内容（默认）。例："猫笔刀怎么看待月光族"

规则：
- 不确定时返回 qa，confidence 设为 0.5 以下，不要猜测
- 只返回 JSON，不要有任何额外文字

返回格式：{"intent": "<类型>", "confidence": <0.0-1.0>, "reason": "<简短理由>"}"""


class _LLMIntentResponse(BaseModel):
    intent: str
    confidence: float
    reason: str


class LLMClassifier:
    def __init__(self, config: Settings) -> None:
        self._config = config

    def classify(
        self,
        query: str,
        conversation_history: list[dict] | None = None,
    ) -> IntentResult:
        client = OpenAI(
            base_url=self._config.effective_llm_base_url,
            api_key=self._config.effective_llm_api_key,
        )
        messages: list[dict] = [{"role": "system", "content": _INTENT_SYSTEM_PROMPT}]
        if conversation_history:
            messages.extend(conversation_history[-4:])
        messages.append({"role": "user", "content": f"query: {query}"})

        raw = ""
        try:
            response = client.chat.completions.create(
                model=self._config.effective_intent_llm_model,
                messages=messages,
                temperature=0,
                max_tokens=128,
            )
            raw = response.choices[0].message.content or ""
            parsed = _LLMIntentResponse.model_validate_json(raw)
            intent_type = IntentType(parsed.intent)
            return IntentResult(
                intent=intent_type,
                confidence=parsed.confidence,
                method="llm",
                raw_response=raw,
                metadata={"reason": parsed.reason},
            )
        except (ValidationError, ValueError, KeyError) as exc:
            logger.warning("Intent LLM parse failed: %s | raw=%r", exc, raw)
        except Exception as exc:
            logger.warning("Intent LLM call failed: %s", exc)

        return IntentResult(
            intent=IntentType.QA,
            confidence=0.0,
            method="fallback",
            raw_response=raw or None,
        )


class IntentRouter:
    def __init__(self, config: Settings) -> None:
        self._rule = RuleClassifier()
        self._llm = LLMClassifier(config)
        self._threshold = config.INTENT_CONFIDENCE_THRESHOLD

    def classify(
        self,
        query: str,
        conversation_history: list[dict] | None = None,
    ) -> IntentResult:
        result = self._rule.classify(query)
        if result is not None:
            return result

        result = self._llm.classify(query, conversation_history)
        if result.confidence < self._threshold:
            return IntentResult(
                intent=IntentType.QA,
                confidence=result.confidence,
                method="fallback",
                raw_response=result.raw_response,
                metadata=result.metadata,
            )
        return result
