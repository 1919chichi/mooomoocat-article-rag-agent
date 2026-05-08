from __future__ import annotations

from pathlib import Path

import pytest

from mooomoocatrag.ingest.parser import parse_article


class TestParser:
    def test_parse_markdown_with_frontmatter_title(self, sample_md_path):
        result = parse_article(str(sample_md_path), 'markdown')
        assert result.title == '测试文章标题'
        assert result.file_type == 'markdown'
        assert '---' not in result.body
        assert result.body.startswith('# 第一章 概述')

    def test_parse_markdown_with_h1_fallback(self, tmp_path):
        md_content = """# 这是H1标题

这是正文内容。
"""
        md_file = tmp_path / "test.md"
        md_file.write_text(md_content, encoding='utf-8')

        result = parse_article(str(md_file), 'markdown')
        assert result.title == '这是H1标题'

    def test_parse_markdown_filename_fallback(self, tmp_path):
        md_content = """这是正文内容。
"""
        md_file = tmp_path / "我的文件.md"
        md_file.write_text(md_content, encoding='utf-8')

        result = parse_article(str(md_file), 'markdown')
        assert result.title == '我的文件'

    def test_parse_text_filename_as_title(self, sample_txt_path):
        result = parse_article(str(sample_txt_path), 'text')
        assert result.title == 'sample'
        assert result.file_type == 'text'

    def test_parse_removes_extra_blank_lines(self, sample_md_path):
        result = parse_article(str(sample_md_path), 'markdown')
        assert '\n\n\n' not in result.body

    def test_parse_empty_file(self, tmp_path):
        md_file = tmp_path / "empty.md"
        md_file.write_text('', encoding='utf-8')

        result = parse_article(str(md_file), 'markdown')
        assert result.title == 'empty'
        assert result.body == ''

    def test_parse_body_clean(self, tmp_path):
        md_content = """# 标题

第一段文字。


第二段文字。


第三段文字。
"""
        md_file = tmp_path / "clean.md"
        md_file.write_text(md_content, encoding='utf-8')

        result = parse_article(str(md_file), 'markdown')
        lines = result.body.splitlines()
        blank_count = sum(1 for line in lines if line.strip() == '')
        consecutive_blank = False
        for line in lines:
            if line.strip() == '':
                assert not consecutive_blank, "连续空行未被去除"
                consecutive_blank = True
            else:
                consecutive_blank = False

    def test_parse_preserves_source_relative_path_when_provided(self, tmp_path):
        source_root = tmp_path / "articles"
        nested_dir = source_root / "nested"
        nested_dir.mkdir(parents=True)
        md_file = nested_dir / "post.md"
        md_file.write_text("# 子目录文章\n\n正文内容。", encoding="utf-8")

        result = parse_article(
            str(md_file),
            "markdown",
            source_root=str(source_root),
        )

        assert result.source_rel_path == "nested/post.md"
