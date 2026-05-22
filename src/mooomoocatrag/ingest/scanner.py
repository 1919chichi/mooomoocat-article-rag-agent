from __future__ import annotations

import hashlib
import os
from datetime import datetime
from pathlib import Path

from mooomoocatrag.models import ArticleMeta


def scan_articles(source_dir: str) -> list[ArticleMeta]:
    """递归扫描目录，收集 .md/.txt 文件元数据，不解析正文内容。

    title 字段仅为文件名占位符，ingest 流程会用 parse_article() 结果覆盖为真实标题。
    """
    articles: list[ArticleMeta] = []
    source_path = Path(source_dir)

    for root, dirs, files in os.walk(source_path):
        # 跳过隐藏目录（.git、.obsidian、.trash 等），避免扫描版本控制或系统目录
        dirs[:] = [d for d in dirs if not d.startswith('.')]

        for filename in files:
            if not filename.endswith(('.md', '.txt')):
                continue

            file_path = Path(root) / filename
            rel_path = file_path.relative_to(source_path)
            file_type = 'markdown' if filename.endswith('.md') else 'text'

            stat = file_path.stat()
            modified_time = datetime.fromtimestamp(stat.st_mtime)

            # 必须用 read_bytes()：read_text() 会剥离 BOM，导致与 parser.py 的 hash 不一致
            try:
                raw_content = file_path.read_bytes()
                raw_content.decode('utf-8')  # 仅校验 UTF-8 合法性，不使用解码结果
            except UnicodeDecodeError as e:
                raise ValueError(f"文件编码错误 {file_path}: {e}")

            content_hash = hashlib.sha256(raw_content).hexdigest()

            # 文件移动或重命名视为新文章，旧路径按删除处理
            article_id = hashlib.sha256(str(rel_path).encode('utf-8')).hexdigest()

            title = file_path.stem

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
