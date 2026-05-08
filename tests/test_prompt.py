from __future__ import annotations

import pytest

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChunkMeta, RetrievalResult
from mooomoocatrag.rag.prompt import build_rag_prompt, format_citations, SYSTEM_PROMPT


@pytest.fixture
def sample_chunk():
    return ChunkMeta(
        chunk_id="article-1_0",
        article_id="article-1",
        chunk_index=0,
        nearest_heading="Introduction",
        text="This is a test article about cats.",
        source_rel_path="articles/cats.md",
        title="All About Cats",
        content_hash="hash123",
        embedding_model="test-model",
        embedding_dimension=1536,
    )


@pytest.fixture
def sample_results(sample_chunk):
    chunk2 = ChunkMeta(
        chunk_id="article-1_1",
        article_id="article-1",
        chunk_index=1,
        nearest_heading="Cat Behavior",
        text="Cats love to nap in sunny spots.",
        source_rel_path="articles/cats.md",
        title="All About Cats",
        content_hash="hash123",
        embedding_model="test-model",
        embedding_dimension=1536,
    )
    return [
        RetrievalResult(chunk=sample_chunk, similarity=0.95),
        RetrievalResult(chunk=chunk2, similarity=0.85),
    ]


class TestBuildRagPrompt:
    def test_system_prompt_contains_required_instructions(self):
        """Test system prompt contains necessary instructions"""
        assert "猫笔刀文章库" in SYSTEM_PROMPT
        assert "优先依据给定的文章片段" in SYSTEM_PROMPT
        assert "[1]、[2]" in SYSTEM_PROMPT or "[1]" in SYSTEM_PROMPT
        assert "没有出现在文章片段中的内容" in SYSTEM_PROMPT
        assert "不足以回答" in SYSTEM_PROMPT

    def test_prompt_structure_with_results(self, sample_results):
        """Test prompt structure when results are provided"""
        query = "What do cats like to do?"
        messages = build_rag_prompt(query, sample_results)

        # Should have system + user message
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_retrieved_chunks_numbered_correctly(self, sample_results):
        """Test retrieved chunks are numbered correctly"""
        query = "What do cats like to do?"
        messages = build_rag_prompt(query, sample_results)

        user_content = messages[1]["content"]
        assert "[1]" in user_content
        assert "[2]" in user_content
        # Should contain the actual text
        assert "This is a test article about cats" in user_content
        assert "Cats love to nap" in user_content

    def test_prompt_contains_query(self, sample_results):
        """Test user message contains the query"""
        query = "What do cats like to do?"
        messages = build_rag_prompt(query, sample_results)

        user_content = messages[1]["content"]
        assert "用户问题：" in user_content
        assert query in user_content

    def test_empty_results_prompt(self):
        """Test prompt when no results are retrieved"""
        query = "What about dogs?"
        messages = build_rag_prompt(query, [])

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

        user_content = messages[1]["content"]
        assert "用户问题：" in user_content
        assert query in user_content
        assert "没有找到足够依据" in user_content

    def test_history_included_when_present(self, sample_results):
        """Test chat history is included in prompt"""
        query = "What do cats like to do?"
        history = [
            {"role": "user", "content": "Tell me about cats"},
            {"role": "assistant", "content": "Cats are great!"},
        ]
        messages = build_rag_prompt(query, sample_results, history)

        # Should have system + 2 history messages + user
        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"
        assert messages[3]["role"] == "user"

    def test_history_only_includes_user_assistant(self, sample_results):
        """Test history only includes valid roles"""
        query = "What do cats like to do?"
        history = [
            {"role": "system", "content": "You are a helpful assistant"},  # Should be ignored
            {"role": "user", "content": "Tell me about cats"},
            {"role": "assistant", "content": "Cats are great!"},
            {"role": "invalid", "content": "Should be ignored"},
        ]
        messages = build_rag_prompt(query, sample_results, history)

        # Only user and assistant should be included
        roles = [m["role"] for m in messages]
        assert "system" in roles
        # Count non-system roles
        non_system = [r for r in roles if r != "system"]
        assert len(non_system) == 3  # user, assistant, user


class TestFormatCitations:
    def test_citation_format_basic(self, sample_results):
        """Test basic citation format"""
        citations = format_citations(sample_results)

        assert len(citations) == 2
        # Should contain relative path, not absolute
        assert "articles/cats.md" in citations[0]
        assert "/Users/" not in citations[0]
        assert "/home/" not in citations[0]

    def test_citation_contains_chunk_index(self, sample_results):
        """Test citation contains chunk index"""
        citations = format_citations(sample_results)

        assert "chunk 0" in citations[0]
        assert "chunk 1" in citations[1]

    def test_citation_contains_heading(self, sample_results):
        """Test citation contains nearest heading"""
        citations = format_citations(sample_results)

        assert "小标题：Introduction" in citations[0]
        assert "小标题：Cat Behavior" in citations[1]

    def test_citation_with_empty_heading(self):
        """Test citation with no heading"""
        chunk = ChunkMeta(
            chunk_id="article-1_0",
            article_id="article-1",
            chunk_index=0,
            nearest_heading="",
            text="Some text",
            source_rel_path="articles/test.md",
            title="Test",
            content_hash="hash123",
            embedding_model="test",
            embedding_dimension=1536,
        )
        result = [RetrievalResult(chunk=chunk, similarity=0.9)]
        citations = format_citations(result)

        assert "小标题：无" in citations[0]

    def test_citation_numbering(self, sample_results):
        """Test citations are numbered starting from 1"""
        citations = format_citations(sample_results)

        assert citations[0].startswith("[1]")
        assert citations[1].startswith("[2]")

    def test_empty_results_returns_empty_citations(self):
        """Test empty results returns empty citations list"""
        citations = format_citations([])
        assert citations == []
