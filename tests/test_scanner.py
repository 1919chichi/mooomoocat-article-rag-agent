from __future__ import annotations

import hashlib

import pytest

from mooomoocatrag.ingest.scanner import scan_articles


class TestScanner:
    def test_scans_markdown_and_text_recursively(self, tmp_path):
        source_root = tmp_path / "articles"
        nested_dir = source_root / "nested"
        hidden_dir = source_root / ".git"
        nested_dir.mkdir(parents=True)
        hidden_dir.mkdir(parents=True)

        md_file = nested_dir / "post.md"
        txt_file = source_root / "note.txt"
        ignored_file = hidden_dir / "ignored.md"
        other_file = source_root / "image.png"

        md_content = "# 标题\n\n正文"
        txt_content = "纯文本正文"
        md_file.write_text(md_content, encoding="utf-8")
        txt_file.write_text(txt_content, encoding="utf-8")
        ignored_file.write_text("# ignored", encoding="utf-8")
        other_file.write_text("not an article", encoding="utf-8")

        articles = scan_articles(str(source_root))

        rel_paths = {article.source_rel_path for article in articles}
        assert rel_paths == {"nested/post.md", "note.txt"}

        md_article = next(a for a in articles if a.source_rel_path == "nested/post.md")
        assert md_article.file_type == "markdown"
        assert md_article.content_hash == hashlib.sha256(
            md_content.encode("utf-8")
        ).hexdigest()

        txt_article = next(a for a in articles if a.source_rel_path == "note.txt")
        assert txt_article.file_type == "text"

    def test_reports_non_utf8_file_with_clear_error(self, tmp_path):
        source_root = tmp_path / "articles"
        source_root.mkdir()
        bad_file = source_root / "bad.md"
        bad_file.write_bytes(b"\xff\xfe\xfd")

        with pytest.raises(ValueError, match="文件编码错误"):
            scan_articles(str(source_root))
