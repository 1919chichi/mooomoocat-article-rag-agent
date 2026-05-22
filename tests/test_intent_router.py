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
