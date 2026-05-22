# Intent Recognition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a hybrid rule/LLM intent router to `chat_turn` that routes chitchat, off-topic, list, summarize, and QA queries to dedicated handlers, eliminating the current "always retrieves even for greetings" behavior.

**Architecture:** An `IntentRouter` (rules-first, LLM fallback) classifies each query into one of five `IntentType` values before dispatch. Each handler is an independent function in `rag/intent/handlers/`. `chat.py` becomes a thin dispatcher. Rules cover high-confidence cases (greetings, list prefixes, summarize prefixes) at zero cost; ambiguous queries fall to a small LLM model via structured JSON output.

**Tech Stack:** Python, pydantic-settings (existing), openai SDK (existing), pydantic v2 `model_validate_json`, pytest + unittest.mock (existing patterns in `tests/`)

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `src/mooomoocatrag/config.py` | Add `INTENT_LLM_MODEL`, `INTENT_CONFIDENCE_THRESHOLD`, `effective_intent_llm_model` |
| Create | `src/mooomoocatrag/rag/intent/__init__.py` | Re-export public API |
| Create | `src/mooomoocatrag/rag/intent/types.py` | `IntentType` enum + `IntentResult` dataclass |
| Create | `src/mooomoocatrag/rag/intent/router.py` | `RuleClassifier`, `LLMClassifier`, `IntentRouter` |
| Create | `src/mooomoocatrag/rag/intent/handlers/__init__.py` | Handler registry / re-exports |
| Create | `src/mooomoocatrag/rag/intent/handlers/off_topic.py` | Fixed-template rejection handler |
| Create | `src/mooomoocatrag/rag/intent/handlers/chitchat.py` | Small-model chitchat handler |
| Create | `src/mooomoocatrag/rag/intent/handlers/list.py` | Manifest metadata list handler |
| Create | `src/mooomoocatrag/rag/intent/handlers/summarize.py` | RAG + summarize-prompt handler |
| Create | `src/mooomoocatrag/rag/intent/handlers/qa.py` | Full RAG QA handler (core logic moved from chat.py) |
| Modify | `src/mooomoocatrag/rag/chat.py` | Thin dispatcher; keeps public API for backward compat |
| Create | `tests/fixtures/intent_cases.json` | Golden dataset (≥30 cases) |
| Create | `tests/test_intent_router.py` | Unit tests for rules + router fallback logic |
| Modify | `tests/test_chat.py` | Mock `IntentRouter.classify` so existing tests target QA handler |

---

## Task 1: Add Intent Config Fields

**Files:**
- Modify: `src/mooomoocatrag/config.py`

- [ ] **Step 1: Add two fields and one property to `Settings`**

  In `src/mooomoocatrag/config.py`, add after `LLM_CONTEXT_WINDOW: int = 32768`:

  ```python
  INTENT_LLM_MODEL: str = ""
  INTENT_CONFIDENCE_THRESHOLD: float = 0.6
  ```

  Add after the `effective_llm_api_key` property (line ~99):

  ```python
  @property
  def effective_intent_llm_model(self) -> str:
      return self.INTENT_LLM_MODEL or self.LLM_MODEL
  ```

- [ ] **Step 2: Verify no import errors**

  ```bash
  python -c "from mooomoocatrag.config import Settings; s = Settings(); print(s.INTENT_CONFIDENCE_THRESHOLD, s.effective_intent_llm_model)"
  ```

  Expected: `0.6 ` (empty string when LLM_MODEL not set)

- [ ] **Step 3: Commit**

  ```bash
  git add src/mooomoocatrag/config.py
  git commit -m "feat(intent): add INTENT_LLM_MODEL and INTENT_CONFIDENCE_THRESHOLD config"
  ```

---

## Task 2: Create `intent/types.py`

**Files:**
- Create: `src/mooomoocatrag/rag/intent/__init__.py`
- Create: `src/mooomoocatrag/rag/intent/types.py`

- [ ] **Step 1: Create directory and `__init__.py` placeholder**

  ```bash
  mkdir -p src/mooomoocatrag/rag/intent/handlers
  touch src/mooomoocatrag/rag/intent/__init__.py
  touch src/mooomoocatrag/rag/intent/handlers/__init__.py
  ```

- [ ] **Step 2: Write `types.py`**

  Create `src/mooomoocatrag/rag/intent/types.py`:

  ```python
  from __future__ import annotations

  from dataclasses import dataclass, field
  from enum import Enum
  from typing import Literal


  class IntentType(str, Enum):
      CHITCHAT  = "chitchat"
      OFF_TOPIC = "off_topic"
      LIST      = "list"
      SUMMARIZE = "summarize"
      QA        = "qa"


  @dataclass
  class IntentResult:
      intent:       IntentType
      confidence:   float
      method:       Literal["rule", "llm", "fallback"]
      raw_response: str | None = None
      metadata:     dict = field(default_factory=dict)
  ```

- [ ] **Step 3: Verify import**

  ```bash
  python -c "from mooomoocatrag.rag.intent.types import IntentType, IntentResult; print(IntentType.QA)"
  ```

  Expected: `IntentType.QA`

- [ ] **Step 4: Commit**

  ```bash
  git add src/mooomoocatrag/rag/intent/
  git commit -m "feat(intent): add IntentType enum and IntentResult dataclass"
  ```

---

## Task 3: RuleClassifier

**Files:**
- Create: `src/mooomoocatrag/rag/intent/router.py`
- Create: `tests/test_intent_router.py`

- [ ] **Step 1: Write failing tests for RuleClassifier**

  Create `tests/test_intent_router.py`:

  ```python
  from __future__ import annotations

  import pytest
  from unittest.mock import MagicMock, patch

  from mooomoocatrag.rag.intent.types import IntentType
  from mooomoocatrag.rag.intent.router import RuleClassifier


  class TestRuleClassifier:
      def setup_method(self):
          self.clf = RuleClassifier()

      def test_chitchat_greeting_nihao(self):
          result = self.clf.classify("你好")
          assert result is not None
          assert result.intent == IntentType.CHITCHAT
          assert result.method == "rule"
          assert result.metadata["rule_id"] == "chitchat_greeting"

      def test_chitchat_greeting_xiexie(self):
          result = self.clf.classify("谢谢")
          assert result is not None
          assert result.intent == IntentType.CHITCHAT

      def test_chitchat_greeting_zaijian(self):
          result = self.clf.classify("再见")
          assert result is not None
          assert result.intent == IntentType.CHITCHAT

      def test_chitchat_long_query_not_matched(self):
          # Long queries with greeting words should NOT be classified as CHITCHAT by rules
          result = self.clf.classify("你好，帮我找一篇关于投资理财的文章")
          assert result is None  # Falls through to LLM

      def test_list_liejv(self):
          result = self.clf.classify("列举所有关于理财的文章")
          assert result is not None
          assert result.intent == IntentType.LIST
          assert result.method == "rule"
          assert result.metadata["rule_id"] == "list_articles"

      def test_list_younaexie(self):
          result = self.clf.classify("有哪些关于投资的文章")
          assert result is not None
          assert result.intent == IntentType.LIST

      def test_list_liechusuoyou(self):
          result = self.clf.classify("列出所有讲消费观的文章")
          assert result is not None
          assert result.intent == IntentType.LIST

      def test_summarize_zongjie(self):
          result = self.clf.classify("总结一下猫笔刀关于消费观的观点")
          assert result is not None
          assert result.intent == IntentType.SUMMARIZE
          assert result.method == "rule"
          assert result.metadata["rule_id"] == "summarize_articles"

      def test_summarize_zhaiyao(self):
          result = self.clf.classify("摘要一下这篇文章的核心内容")
          assert result is not None
          assert result.intent == IntentType.SUMMARIZE

      def test_qa_no_match(self):
          result = self.clf.classify("猫笔刀怎么看待月光族")
          assert result is None

      def test_qa_complex_question_no_match(self):
          result = self.clf.classify("猫笔刀有没有写过关于职场发展的内容")
          assert result is None

      def test_fullwidth_normalized(self):
          # Full-width "你好" should still match
          result = self.clf.classify("你好")
          assert result is not None
          assert result.intent == IntentType.CHITCHAT
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  pytest tests/test_intent_router.py -v 2>&1 | head -20
  ```

  Expected: `ModuleNotFoundError` or similar — `router.py` doesn't exist yet.

- [ ] **Step 3: Create `router.py` with `RuleClassifier`**

  Create `src/mooomoocatrag/rag/intent/router.py`:

  ```python
  from __future__ import annotations

  import re
  import unicodedata
  from typing import TYPE_CHECKING

  from mooomoocatrag.rag.intent.types import IntentResult, IntentType

  if TYPE_CHECKING:
      from mooomoocatrag.config import Settings

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

          # CHITCHAT: short query whose full text is in the whitelist
          if len(q) <= 10 and q in _CHITCHAT_WHITELIST:
              return IntentResult(
                  intent=IntentType.CHITCHAT,
                  confidence=0.95,
                  method="rule",
                  metadata={"rule_id": "chitchat_greeting"},
              )

          # LIST: query starts with a list verb and contains an article keyword
          if _LIST_PATTERN.search(q):
              return IntentResult(
                  intent=IntentType.LIST,
                  confidence=0.9,
                  method="rule",
                  metadata={"rule_id": "list_articles"},
              )

          # SUMMARIZE: query starts with a summarize verb
          if _SUMMARIZE_PATTERN.match(q):
              return IntentResult(
                  intent=IntentType.SUMMARIZE,
                  confidence=0.9,
                  method="rule",
                  metadata={"rule_id": "summarize_articles"},
              )

          return None
  ```

- [ ] **Step 4: Run tests and confirm they pass**

  ```bash
  pytest tests/test_intent_router.py::TestRuleClassifier -v
  ```

  Expected: all 12 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/mooomoocatrag/rag/intent/router.py tests/test_intent_router.py
  git commit -m "feat(intent): add RuleClassifier with whitelist and regex rules"
  ```

---

## Task 4: LLMClassifier + IntentRouter

**Files:**
- Modify: `src/mooomoocatrag/rag/intent/router.py`
- Modify: `tests/test_intent_router.py`

- [ ] **Step 1: Add failing tests for LLMClassifier and IntentRouter**

  Append to `tests/test_intent_router.py`:

  ```python
  from mooomoocatrag.config import Settings
  from mooomoocatrag.rag.intent.router import IntentRouter, LLMClassifier


  @pytest.fixture
  def settings():
      return Settings(
          LLM_MODEL="test-model",
          LLM_BASE_URL="https://api.test.com",
          LLM_API_KEY="test-key",
          INTENT_CONFIDENCE_THRESHOLD=0.6,
      )


  class TestLLMClassifier:
      @patch("mooomoocatrag.rag.intent.router.OpenAI")
      def test_valid_response_qa(self, mock_openai_cls, settings):
          mock_client = MagicMock()
          mock_openai_cls.return_value = mock_client
          mock_client.chat.completions.create.return_value = MagicMock(
              choices=[MagicMock(message=MagicMock(
                  content='{"intent": "qa", "confidence": 0.9, "reason": "direct question"}'
              ))]
          )
          clf = LLMClassifier(settings)
          result = clf.classify("猫笔刀怎么看待月光族")
          assert result.intent == IntentType.QA
          assert result.confidence == 0.9
          assert result.method == "llm"

      @patch("mooomoocatrag.rag.intent.router.OpenAI")
      def test_valid_response_off_topic(self, mock_openai_cls, settings):
          mock_client = MagicMock()
          mock_openai_cls.return_value = mock_client
          mock_client.chat.completions.create.return_value = MagicMock(
              choices=[MagicMock(message=MagicMock(
                  content='{"intent": "off_topic", "confidence": 0.85, "reason": "unrelated"}'
              ))]
          )
          clf = LLMClassifier(settings)
          result = clf.classify("帮我写一首诗")
          assert result.intent == IntentType.OFF_TOPIC
          assert result.method == "llm"

      @patch("mooomoocatrag.rag.intent.router.OpenAI")
      def test_invalid_json_falls_back_to_qa(self, mock_openai_cls, settings):
          mock_client = MagicMock()
          mock_openai_cls.return_value = mock_client
          mock_client.chat.completions.create.return_value = MagicMock(
              choices=[MagicMock(message=MagicMock(content="not json at all"))]
          )
          clf = LLMClassifier(settings)
          result = clf.classify("any query")
          assert result.intent == IntentType.QA
          assert result.method == "fallback"

      @patch("mooomoocatrag.rag.intent.router.OpenAI")
      def test_llm_exception_falls_back_to_qa(self, mock_openai_cls, settings):
          mock_client = MagicMock()
          mock_openai_cls.return_value = mock_client
          mock_client.chat.completions.create.side_effect = RuntimeError("timeout")
          clf = LLMClassifier(settings)
          result = clf.classify("any query")
          assert result.intent == IntentType.QA
          assert result.method == "fallback"


  class TestIntentRouter:
      @patch("mooomoocatrag.rag.intent.router.OpenAI")
      def test_rule_takes_priority_llm_not_called(self, mock_openai_cls, settings):
          router = IntentRouter(settings)
          result = router.classify("你好")
          mock_openai_cls.assert_not_called()
          assert result.intent == IntentType.CHITCHAT
          assert result.method == "rule"

      @patch("mooomoocatrag.rag.intent.router.OpenAI")
      def test_falls_back_to_llm_for_ambiguous(self, mock_openai_cls, settings):
          mock_client = MagicMock()
          mock_openai_cls.return_value = mock_client
          mock_client.chat.completions.create.return_value = MagicMock(
              choices=[MagicMock(message=MagicMock(
                  content='{"intent": "qa", "confidence": 0.8, "reason": "question"}'
              ))]
          )
          router = IntentRouter(settings)
          result = router.classify("猫笔刀怎么看待月光族")
          mock_openai_cls.assert_called_once()
          assert result.intent == IntentType.QA

      @patch("mooomoocatrag.rag.intent.router.OpenAI")
      def test_low_confidence_llm_demoted_to_fallback_qa(self, mock_openai_cls, settings):
          mock_client = MagicMock()
          mock_openai_cls.return_value = mock_client
          mock_client.chat.completions.create.return_value = MagicMock(
              choices=[MagicMock(message=MagicMock(
                  content='{"intent": "chitchat", "confidence": 0.4, "reason": "unsure"}'
              ))]
          )
          router = IntentRouter(settings)
          result = router.classify("some ambiguous query")
          assert result.intent == IntentType.QA
          assert result.method == "fallback"
  ```

- [ ] **Step 2: Run to confirm tests fail**

  ```bash
  pytest tests/test_intent_router.py::TestLLMClassifier tests/test_intent_router.py::TestIntentRouter -v 2>&1 | head -20
  ```

  Expected: `ImportError` for `LLMClassifier`, `IntentRouter`.

- [ ] **Step 3: Append LLMClassifier and IntentRouter to `router.py`**

  Append to `src/mooomoocatrag/rag/intent/router.py`:

  ```python
  import logging

  from openai import OpenAI
  from pydantic import BaseModel, ValidationError

  from mooomoocatrag.config import Settings

  logger = logging.getLogger(__name__)

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
  ```

- [ ] **Step 4: Run all intent router tests**

  ```bash
  pytest tests/test_intent_router.py -v
  ```

  Expected: all tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/mooomoocatrag/rag/intent/router.py tests/test_intent_router.py
  git commit -m "feat(intent): add LLMClassifier and IntentRouter"
  ```

---

## Task 5: Update `intent/__init__.py`

**Files:**
- Modify: `src/mooomoocatrag/rag/intent/__init__.py`

- [ ] **Step 1: Export public API**

  Write `src/mooomoocatrag/rag/intent/__init__.py`:

  ```python
  from mooomoocatrag.rag.intent.router import IntentRouter
  from mooomoocatrag.rag.intent.types import IntentResult, IntentType

  __all__ = ["IntentRouter", "IntentResult", "IntentType"]
  ```

- [ ] **Step 2: Verify import**

  ```bash
  python -c "from mooomoocatrag.rag.intent import IntentRouter, IntentType, IntentResult; print('ok')"
  ```

  Expected: `ok`

- [ ] **Step 3: Commit**

  ```bash
  git add src/mooomoocatrag/rag/intent/__init__.py
  git commit -m "feat(intent): export public API from intent package"
  ```

---

## Task 6: Off-topic and Chitchat Handlers

**Files:**
- Modify: `src/mooomoocatrag/rag/intent/handlers/__init__.py`
- Create: `src/mooomoocatrag/rag/intent/handlers/off_topic.py`
- Create: `src/mooomoocatrag/rag/intent/handlers/chitchat.py`

- [ ] **Step 1: Write `off_topic.py`**

  Create `src/mooomoocatrag/rag/intent/handlers/off_topic.py`:

  ```python
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
  ```

- [ ] **Step 2: Write `chitchat.py`**

  Create `src/mooomoocatrag/rag/intent/handlers/chitchat.py`:

  ```python
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
  ```

- [ ] **Step 3: Verify imports**

  ```bash
  python -c "from mooomoocatrag.rag.intent.handlers.off_topic import handle_off_topic; from mooomoocatrag.rag.intent.handlers.chitchat import handle_chitchat; print('ok')"
  ```

  Expected: `ok`

- [ ] **Step 4: Commit**

  ```bash
  git add src/mooomoocatrag/rag/intent/handlers/off_topic.py src/mooomoocatrag/rag/intent/handlers/chitchat.py
  git commit -m "feat(intent): add off_topic and chitchat handlers"
  ```

---

## Task 7: List Handler

**Files:**
- Create: `src/mooomoocatrag/rag/intent/handlers/list.py`

- [ ] **Step 1: Write failing test**

  Append to `tests/test_intent_router.py`:

  ```python
  from mooomoocatrag.models import IndexManifest
  from mooomoocatrag.rag.intent.handlers.list import handle_list


  class TestListHandler:
      def _manifest_with_articles(self):
          return IndexManifest(
              articles={
                  "art-1": {
                      "title": "理财入门",
                      "source_rel_path": "articles/finance.md",
                      "content_hash": "h1",
                  },
                  "art-2": {
                      "title": "消费观念",
                      "source_rel_path": "articles/consume.md",
                      "content_hash": "h2",
                  },
                  "art-del": {
                      "title": "已删除",
                      "source_rel_path": "articles/del.md",
                      "content_hash": "h3",
                      "deleted": True,
                  },
              }
          )

      def test_returns_non_deleted_articles(self):
          manifest = self._manifest_with_articles()
          response = handle_list("有哪些文章", manifest)
          assert response.intent == "list"
          assert "理财入门" in response.answer
          assert "消费观念" in response.answer
          assert "已删除" not in response.answer

      def test_retrieved_count_excludes_deleted(self):
          manifest = self._manifest_with_articles()
          response = handle_list("有哪些文章", manifest)
          assert response.retrieved_count == 2

      def test_empty_manifest(self):
          manifest = IndexManifest(articles={})
          response = handle_list("有哪些文章", manifest)
          assert response.intent == "list"
          assert "为空" in response.answer
          assert response.retrieved_count == 0
  ```

- [ ] **Step 2: Run to confirm failure**

  ```bash
  pytest tests/test_intent_router.py::TestListHandler -v 2>&1 | head -10
  ```

  Expected: `ImportError` for `handle_list`.

- [ ] **Step 3: Write `list.py`**

  Create `src/mooomoocatrag/rag/intent/handlers/list.py`:

  ```python
  from __future__ import annotations

  from mooomoocatrag.models import ChatResponse, IndexManifest


  def handle_list(query: str, manifest: IndexManifest) -> ChatResponse:
      articles = [
          entry
          for entry in manifest.articles.values()
          if not entry.get("deleted")
      ]
      if not articles:
          return ChatResponse(
              answer="猫笔刀文章库目前为空。",
              citations=[],
              retrieved_count=0,
              intent="list",
          )

      lines = ["以下是猫笔刀文章库中的文章列表：\n"]
      for i, entry in enumerate(articles, 1):
          title = entry.get("title", "未知标题")
          path = entry.get("source_rel_path", "")
          lines.append(f"{i}. {title}（{path}）")

      return ChatResponse(
          answer="\n".join(lines),
          citations=[],
          retrieved_count=len(articles),
          intent="list",
      )
  ```

- [ ] **Step 4: Run tests**

  ```bash
  pytest tests/test_intent_router.py::TestListHandler -v
  ```

  Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add src/mooomoocatrag/rag/intent/handlers/list.py tests/test_intent_router.py
  git commit -m "feat(intent): add list handler with manifest metadata query"
  ```

---

## Task 8: Summarize Handler

**Files:**
- Create: `src/mooomoocatrag/rag/intent/handlers/summarize.py`

- [ ] **Step 1: Write `summarize.py`**

  Create `src/mooomoocatrag/rag/intent/handlers/summarize.py`:

  ```python
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
  ```

- [ ] **Step 2: Verify import**

  ```bash
  python -c "from mooomoocatrag.rag.intent.handlers.summarize import handle_summarize; print('ok')"
  ```

  Expected: `ok`

- [ ] **Step 3: Commit**

  ```bash
  git add src/mooomoocatrag/rag/intent/handlers/summarize.py
  git commit -m "feat(intent): add summarize handler with RAG + summary prompt"
  ```

---

## Task 9: QA Handler (move core logic from chat.py)

**Files:**
- Create: `src/mooomoocatrag/rag/intent/handlers/qa.py`

- [ ] **Step 1: Write `qa.py`**

  The QA handler contains exactly the current body of `chat_turn` in `chat.py` (minus the routing that will remain in `chat.py`). Create `src/mooomoocatrag/rag/intent/handlers/qa.py`:

  ```python
  from __future__ import annotations

  import math

  from openai import OpenAI

  from mooomoocatrag.config import Settings
  from mooomoocatrag.models import ChatResponse, IndexManifest
  from mooomoocatrag.rag.prompt import build_rag_prompt, format_citations
  from mooomoocatrag.rag.retriever import retrieve

  INSUFFICIENT_CONTENT_RESPONSE = "当前猫笔刀文章库中没有找到足够依据。"

  _VALID_HISTORY_ROLES = {"user", "assistant"}


  def _estimate_tokens(text: str) -> int:
      return math.ceil(len(text) / 1.5)


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
      system_prompt_tokens = _estimate_tokens(
          "你是一个基于猫笔刀文章库回答问题的 Agent。\n"
          "你必须优先依据给定的文章片段回答。\n"
          "使用 [1]、[2] 等标记引用对应片段。\n"
          "不要把没有出现在文章片段中的内容说成猫笔刀文章观点。\n"
          "如果文章片段不足以回答，直接说明\"当前猫笔刀文章库中没有找到足够依据\"。"
      )

      max_history_messages = config.CHAT_HISTORY_TURNS * 2
      trimmed_history = _recent_valid_history(history, max_history_messages)
      adjusted_results = sorted(results, key=lambda r: r.similarity, reverse=True)

      retrieved_tokens = sum(_estimate_tokens(r.chunk.text) for r in adjusted_results)
      query_tokens = _estimate_tokens(query)
      history_tokens = sum(_estimate_tokens(t.get("content", "")) for t in trimmed_history)
      total_estimated = system_prompt_tokens + retrieved_tokens + query_tokens + history_tokens

      if total_estimated > input_token_budget:
          for keep_count in range(len(adjusted_results), 0, -1):
              test_results = adjusted_results[:keep_count]
              test_tokens = sum(_estimate_tokens(r.chunk.text) for r in test_results)
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
  ```

- [ ] **Step 2: Verify import**

  ```bash
  python -c "from mooomoocatrag.rag.intent.handlers.qa import handle_qa, INSUFFICIENT_CONTENT_RESPONSE; print('ok')"
  ```

  Expected: `ok`

- [ ] **Step 3: Commit**

  ```bash
  git add src/mooomoocatrag/rag/intent/handlers/qa.py
  git commit -m "feat(intent): add QA handler with full RAG pipeline"
  ```

---

## Task 10: Update `handlers/__init__.py`

**Files:**
- Modify: `src/mooomoocatrag/rag/intent/handlers/__init__.py`

- [ ] **Step 1: Write registry exports**

  Write `src/mooomoocatrag/rag/intent/handlers/__init__.py`:

  ```python
  from mooomoocatrag.rag.intent.handlers.chitchat import handle_chitchat
  from mooomoocatrag.rag.intent.handlers.list import handle_list
  from mooomoocatrag.rag.intent.handlers.off_topic import handle_off_topic
  from mooomoocatrag.rag.intent.handlers.qa import handle_qa, INSUFFICIENT_CONTENT_RESPONSE
  from mooomoocatrag.rag.intent.handlers.summarize import handle_summarize

  __all__ = [
      "handle_chitchat",
      "handle_list",
      "handle_off_topic",
      "handle_qa",
      "handle_summarize",
      "INSUFFICIENT_CONTENT_RESPONSE",
  ]
  ```

- [ ] **Step 2: Verify**

  ```bash
  python -c "from mooomoocatrag.rag.intent.handlers import handle_qa, handle_chitchat, handle_off_topic, handle_list, handle_summarize; print('ok')"
  ```

  Expected: `ok`

- [ ] **Step 3: Commit**

  ```bash
  git add src/mooomoocatrag/rag/intent/handlers/__init__.py
  git commit -m "feat(intent): export all handlers from handlers package"
  ```

---

## Task 11: Refactor `chat.py` into Dispatcher + Update `test_chat.py`

**Files:**
- Modify: `src/mooomoocatrag/rag/chat.py`
- Modify: `tests/test_chat.py`

- [ ] **Step 1: Rewrite `chat.py`**

  Replace the entire content of `src/mooomoocatrag/rag/chat.py` with:

  ```python
  from __future__ import annotations

  from mooomoocatrag.config import Settings
  from mooomoocatrag.models import ChatResponse, IndexManifest
  from mooomoocatrag.rag.intent import IntentRouter, IntentType
  from mooomoocatrag.rag.intent.handlers import (
      handle_chitchat,
      handle_list,
      handle_off_topic,
      handle_qa,
      handle_summarize,
      INSUFFICIENT_CONTENT_RESPONSE,
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
  ```

- [ ] **Step 2: Update `test_chat.py` — add router mock fixture**

  In `tests/test_chat.py`, add this import at the top:

  ```python
  from mooomoocatrag.rag.intent.types import IntentResult, IntentType
  ```

  Add a `mock_qa_intent` fixture inside `TestChatTurn`:

  ```python
  @pytest.fixture(autouse=True)
  def mock_intent_router(self):
      """Force QA intent so existing tests exercise the QA handler path."""
      qa_result = IntentResult(intent=IntentType.QA, confidence=0.9, method="rule")
      with patch("mooomoocatrag.rag.chat.IntentRouter") as mock_router_cls:
          mock_router_cls.return_value.classify.return_value = qa_result
          yield mock_router_cls
  ```

  Also update the import line (since `retrieve` is now in `handlers/qa.py`, not `chat.py`):

  ```python
  # Old:
  @patch("mooomoocatrag.rag.chat.retrieve")
  # New: patch retrieve where it's actually used
  @patch("mooomoocatrag.rag.intent.handlers.qa.retrieve")
  ```

  Apply that substitution to all `@patch("mooomoocatrag.rag.chat.retrieve")` decorators in the file.

  Also update the `OpenAI` patch path in all decorators:

  ```python
  # Old:
  @patch("mooomoocatrag.rag.chat.OpenAI")
  # New:
  @patch("mooomoocatrag.rag.intent.handlers.qa.OpenAI")
  ```

- [ ] **Step 3: Run full test suite**

  ```bash
  pytest tests/ -v
  ```

  Expected: all existing tests PASS. No regressions.

- [ ] **Step 4: Commit**

  ```bash
  git add src/mooomoocatrag/rag/chat.py tests/test_chat.py
  git commit -m "feat(intent): refactor chat.py to intent dispatcher, update tests"
  ```

---

## Task 12: Golden Dataset + Integration Tests

**Files:**
- Create: `tests/fixtures/intent_cases.json`
- Modify: `tests/test_intent_router.py`

- [ ] **Step 1: Create `tests/fixtures/intent_cases.json`**

  ```json
  [
    {"query": "你好", "expected_intent": "chitchat", "expected_method": "rule"},
    {"query": "谢谢", "expected_intent": "chitchat", "expected_method": "rule"},
    {"query": "再见", "expected_intent": "chitchat", "expected_method": "rule"},
    {"query": "早安", "expected_intent": "chitchat", "expected_method": "rule"},
    {"query": "晚安", "expected_intent": "chitchat", "expected_method": "rule"},
    {"query": "列举所有关于理财的文章", "expected_intent": "list", "expected_method": "rule"},
    {"query": "有哪些关于投资的文章", "expected_intent": "list", "expected_method": "rule"},
    {"query": "列出所有讲消费观的文章", "expected_intent": "list", "expected_method": "rule"},
    {"query": "哪些文章讲了理财", "expected_intent": "list", "expected_method": "rule"},
    {"query": "总结一下猫笔刀关于消费观的文章", "expected_intent": "summarize", "expected_method": "rule"},
    {"query": "摘要一下这篇文章的核心", "expected_intent": "summarize", "expected_method": "rule"},
    {"query": "概括猫笔刀关于职场的观点", "expected_intent": "summarize", "expected_method": "rule"},
    {"query": "你好，帮我找一篇关于投资的文章", "expected_intent": null, "expected_method": null, "note": "rule returns None, falls to LLM"},
    {"query": "猫笔刀怎么看待月光族", "expected_intent": null, "expected_method": null, "note": "QA, goes to LLM"},
    {"query": "猫笔刀有没有写过关于职场发展的内容", "expected_intent": null, "expected_method": null, "note": "QA, goes to LLM"}
  ]
  ```

- [ ] **Step 2: Add golden dataset test to `test_intent_router.py`**

  Append to `tests/test_intent_router.py`:

  ```python
  import json
  from pathlib import Path


  class TestRuleClassifierGoldenDataset:
      """Test RuleClassifier against all golden cases that have a rule-level expectation."""

      def test_golden_rule_cases(self):
          fixture_path = Path(__file__).parent / "fixtures" / "intent_cases.json"
          cases = json.loads(fixture_path.read_text(encoding="utf-8"))
          clf = RuleClassifier()

          rule_cases = [c for c in cases if c.get("expected_method") == "rule"]
          assert len(rule_cases) >= 10, "Need at least 10 rule-level golden cases"

          for case in rule_cases:
              result = clf.classify(case["query"])
              assert result is not None, f"Rule should match: {case['query']!r}"
              assert result.intent.value == case["expected_intent"], (
                  f"query={case['query']!r}: "
                  f"expected {case['expected_intent']}, got {result.intent.value}"
              )
              assert result.method == "rule", f"Expected rule method for {case['query']!r}"

      def test_golden_no_rule_cases(self):
          fixture_path = Path(__file__).parent / "fixtures" / "intent_cases.json"
          cases = json.loads(fixture_path.read_text(encoding="utf-8"))
          clf = RuleClassifier()

          no_rule_cases = [c for c in cases if c.get("expected_method") is None]
          for case in no_rule_cases:
              result = clf.classify(case["query"])
              assert result is None, (
                  f"Rule should NOT match {case['query']!r} "
                  f"(note: {case.get('note', '')}), got {result}"
              )
  ```

- [ ] **Step 3: Run golden dataset tests**

  ```bash
  pytest tests/test_intent_router.py::TestRuleClassifierGoldenDataset -v
  ```

  Expected: both tests PASS.

- [ ] **Step 4: Run full test suite one final time**

  ```bash
  pytest tests/ -v
  ```

  Expected: all tests PASS, zero failures.

- [ ] **Step 5: Commit**

  ```bash
  git add tests/fixtures/intent_cases.json tests/test_intent_router.py
  git commit -m "test(intent): add golden dataset and integration tests for intent router"
  ```

---

## Self-Review Checklist

- [x] **Spec coverage:** All 5 intent types implemented. Rule classifier (3 rules). LLM classifier (structured output, Pydantic, fallback). IntentRouter (rules-first + threshold). Five handlers. `chat.py` refactored. Config items added. Golden dataset created.
- [x] **No placeholders:** All code blocks are complete. No TBD/TODO.
- [x] **Type consistency:** `IntentResult` defined in Task 2, used in Tasks 3/4 and all subsequent tasks. `handle_list(query, manifest)` signature consistent across Task 7 and Task 11. `INSUFFICIENT_CONTENT_RESPONSE` defined in `handlers/qa.py`, re-exported in `chat.py` as `NO_INSUFFICIENT_CONTENTResponse` for backward compat.
- [x] **Test patch paths updated:** `test_chat.py` patches `mooomoocatrag.rag.intent.handlers.qa.retrieve` and `mooomoocatrag.rag.intent.handlers.qa.OpenAI` after the refactor.
