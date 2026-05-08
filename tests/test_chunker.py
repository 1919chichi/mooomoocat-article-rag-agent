from __future__ import annotations

from mooomoocatrag.ingest.chunker import chunk_article
from mooomoocatrag.ingest.parser import parse_article
from mooomoocatrag.models import ParsedArticle


def _parsed_article(body: str) -> ParsedArticle:
    from datetime import datetime

    return ParsedArticle(
        title="测试",
        source_path="/test",
        source_rel_path="test.md",
        file_type="markdown",
        content_hash="abc123",
        modified_time=datetime.now(),
        body=body,
    )


class TestChunker:
    def test_chunk_article_heading_aware(self, sample_md_path, fake_settings):
        parsed = parse_article(str(sample_md_path), 'markdown')
        chunks = chunk_article(parsed, parsed.source_rel_path, fake_settings)

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.article_id == parsed.source_rel_path
            assert chunk.source_rel_path == parsed.source_rel_path
            assert chunk.title == '测试文章标题'

    def test_nearest_heading(self, sample_md_path, fake_settings):
        parsed = parse_article(str(sample_md_path), 'markdown')
        chunks = chunk_article(parsed, parsed.source_rel_path, fake_settings)

        headings = {c.nearest_heading for c in chunks if c.nearest_heading}
        assert '第一章 概述' in headings or '1.1 背景' in headings or any(headings)

    def test_overlap_not_cross_heading_boundary(self, fake_settings):
        fake_settings.CHUNK_TARGET_MAX_CHARS = 65
        fake_settings.CHUNK_OVERLAP = 40

        previous_heading_text = "上一标题专属内容" * 6
        content = f"""# 第一节

第一节正文。

# 第二节

{previous_heading_text}

# 第三节

第三节正文不能包含上一标题内容。
"""
        parsed = _parsed_article(content)
        chunks = chunk_article(parsed, "test", fake_settings)

        third_chunks = [chunk for chunk in chunks if chunk.nearest_heading == "第三节"]

        assert third_chunks
        assert all("上一标题专属内容" not in chunk.text for chunk in third_chunks)

    def test_long_section_chunks_keep_nearest_heading(self, fake_settings):
        fake_settings.CHUNK_TARGET_MAX_CHARS = 120
        fake_settings.CHUNK_OVERLAP = 20

        content = """# 长章节

第一段很长的正文内容，用来触发长章节拆分。""" + "甲" * 90 + """

第二段很长的正文内容，用来触发长章节拆分。""" + "乙" * 90 + """

第三段很长的正文内容，用来触发长章节拆分。""" + "丙" * 90
        parsed = _parsed_article(content)
        chunks = chunk_article(parsed, "test", fake_settings)

        assert len(chunks) > 1
        assert {chunk.nearest_heading for chunk in chunks} == {"长章节"}

    def test_short_section_merge(self, fake_settings):
        fake_settings.CHUNK_TARGET_MIN_CHARS = 300
        fake_settings.CHUNK_TARGET_MAX_CHARS = 600

        short_content = """# 短标题

这是一段很短的正文。

# 另一个短标题

这又是一段很短的正文。
"""
        parsed = _parsed_article(short_content)

        chunks = chunk_article(parsed, "test", fake_settings)
        assert len(chunks) >= 1

    def test_long_chunk_split(self, fake_settings):
        fake_settings.CHUNK_TARGET_MAX_CHARS = 200

        long_content = """# 长段落

""" + "这是一段很长的正文。" * 50

        parsed = _parsed_article(long_content)

        chunks = chunk_article(parsed, "test", fake_settings)
        for chunk in chunks:
            assert len(chunk.text) <= fake_settings.CHUNK_TARGET_MAX_CHARS * 2

    def test_chinese_text_chunk(self, sample_md_path, fake_settings):
        parsed = parse_article(str(sample_md_path), 'markdown')
        chunks = chunk_article(parsed, parsed.source_rel_path, fake_settings)

        assert len(chunks) > 0
        for chunk in chunks:
            assert len(chunk.text) > 0

    def test_empty_body(self, fake_settings):
        parsed = _parsed_article("")

        chunks = chunk_article(parsed, "test", fake_settings)
        assert len(chunks) == 0

    def test_chunk_ids_unique(self, sample_md_path, fake_settings):
        parsed = parse_article(str(sample_md_path), 'markdown')
        chunks = chunk_article(parsed, parsed.source_rel_path, fake_settings)

        chunk_ids = [c.chunk_id for c in chunks]
        assert len(chunk_ids) == len(set(chunk_ids))
