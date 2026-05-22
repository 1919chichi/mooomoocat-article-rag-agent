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
        result = self.clf.classify("你好，帮我找一篇关于投资理财的文章")
        assert result is None

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
        result = self.clf.classify("你好")
        assert result is not None
        assert result.intent == IntentType.CHITCHAT


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
