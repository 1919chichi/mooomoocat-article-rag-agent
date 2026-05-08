from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

from mooomoocatrag.models import ArticleMeta


def scan_articles(source_dir: str) -> list[ArticleMeta]:
    articles: list[ArticleMeta] = []
    source_path = Path(source_dir)

    for root, dirs, files in os.walk(source_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for filename in files:
            if not filename.endswith(('.md', '.txt')):
                continue

            file_path = Path(root) / filename
            rel_path = file_path.relative_to(source_path)
            file_type = 'markdown' if filename.endswith('.md') else 'text'

            stat = file_path.stat()
            modified_time = datetime.fromtimestamp(stat.st_mtime)

            try:
                content = file_path.read_text(encoding='utf-8')
            except UnicodeDecodeError as e:
                raise ValueError(f"文件编码错误 {file_path}: {e}")

            content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

            article_id = hashlib.sha256(str(rel_path).encode('utf-8')).hexdigest()

            title = filename[:-3] if filename.endswith('.md') or filename.endswith('.txt') else filename

            articles.append(ArticleMeta(
                article_id=article_id,
                title=title,
                source_path=str(file_path),
                source_rel_path=str(rel_path),
                file_type=file_type,
                content_hash=content_hash,
                modified_time=modified_time,
                created_at=modified_time,
                updated_at=modified_time,
            ))

    return articles
