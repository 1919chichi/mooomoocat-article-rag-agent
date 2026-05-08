from __future__ import annotations

import hashlib
import re
from pathlib import Path

from mooomoocatrag.models import ParsedArticle


def parse_article(
    file_path: str,
    file_type: str,
    source_root: str | None = None,
    source_rel_path: str | None = None,
) -> ParsedArticle:
    path = Path(file_path)
    raw_content = path.read_bytes()
    content = raw_content.decode('utf-8')
    stat = path.stat()

    from datetime import datetime
    modified_time = datetime.fromtimestamp(stat.st_mtime)

    content_hash = hashlib.sha256(raw_content).hexdigest()

    rel_path = source_rel_path or _relative_path(path, source_root)

    if file_type == 'markdown':
        title, body = _parse_markdown(content, path.stem)
    else:
        title, body = _parse_text(content, path.stem)

    return ParsedArticle(
        title=title,
        source_path=str(path),
        source_rel_path=str(rel_path),
        file_type=file_type,
        content_hash=content_hash,
        modified_time=modified_time,
        body=body,
    )


def _relative_path(path: Path, source_root: str | None) -> str:
    if not source_root:
        return path.name

    try:
        return str(path.relative_to(Path(source_root)))
    except ValueError:
        return path.name


def _parse_markdown(content: str, fallback_title: str) -> tuple[str, str]:
    title = fallback_title
    body = content

    frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)
        title_match = re.search(r'^title:\s*(.+)$', frontmatter, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip().strip('"\'')
        body = content[frontmatter_match.end():]

    heading_match = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
    if heading_match and title == fallback_title:
        h1_title = heading_match.group(1).strip()
        if h1_title:
            title = h1_title

    body = _clean_body(body)

    return title, body


def _parse_text(content: str, fallback_title: str) -> tuple[str, str]:
    title = fallback_title
    body = _clean_body(content)
    return title, body


def _clean_body(text: str) -> str:
    lines = text.splitlines()

    cleaned_lines = []
    prev_empty = False
    for line in lines:
        is_empty = len(line.strip()) == 0
        if is_empty:
            if not prev_empty:
                cleaned_lines.append('')
            prev_empty = True
        else:
            cleaned_lines.append(line)
            prev_empty = False

    if cleaned_lines and cleaned_lines[-1] == '':
        cleaned_lines.pop()

    return '\n'.join(cleaned_lines)
