from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from mooomoocatrag.config import Settings
from mooomoocatrag.models import ChunkMeta, ParsedArticle


@dataclass
class Section:
    heading: str
    level: int
    content: str


def _make_chunk_id(article_id: str, content_hash: str, idx: int) -> str:
    """chunk_id = sha256(article_id + content_hash + chunk_index)，content_hash 变化时 ID 也变。"""
    return hashlib.sha256(f"{article_id}{content_hash}{idx}".encode()).hexdigest()


def chunk_article(parsed: ParsedArticle, article_id: str, config: Settings) -> list[ChunkMeta]:
    """将文章按标题结构切块，短 section 合并，长 section 拆分，支持跨段落 overlap。"""
    sections = _split_by_headings(parsed.body)

    if not sections:
        if parsed.body.strip():
            return [_make_chunk(parsed.body, '', article_id, parsed, 0, config)]
        return []

    chunks: list[ChunkMeta] = []
    current_chunk_parts: list[str] = []
    current_chunk_part_headings: list[str] = []
    current_heading = sections[0].heading if sections else ''
    chunk_start_idx = 0

    min_chars = config.CHUNK_TARGET_MIN_CHARS
    max_chars = config.CHUNK_TARGET_MAX_CHARS
    overlap = config.CHUNK_OVERLAP

    def flush_chunk(parts: list[str], heading: str, idx: int) -> ChunkMeta:
        text = '\n'.join(parts).strip()
        return _make_chunk(text, heading, article_id, parsed, idx, config)

    def _make_chunk(text: str, heading: str, aid: str, pa: ParsedArticle, idx: int, cfg: Settings) -> ChunkMeta:
        return ChunkMeta(
            chunk_id=_make_chunk_id(aid, pa.content_hash, idx),
            article_id=aid,
            chunk_index=idx,
            nearest_heading=heading,
            text=text,
            source_rel_path=pa.source_rel_path,
            title=pa.title,
            content_hash=pa.content_hash,
            embedding_model=cfg.EMBEDDING_MODEL,
            embedding_dimension=0,
        )

    for i, section in enumerate(sections):
        section_text = section.content.strip()
        if not section_text:
            continue

        section_len = len(section_text)

        if section_len > max_chars:
            if current_chunk_parts:
                chunks.append(flush_chunk(current_chunk_parts, current_heading, chunk_start_idx))
                current_chunk_parts = []
                current_chunk_part_headings = []
                chunk_start_idx = len(chunks)

            sub_chunks = _split_long_section(section_text, section.heading, article_id, parsed, config, chunk_start_idx)
            chunks.extend(sub_chunks)
            chunk_start_idx = len(chunks)
            current_heading = sections[i + 1].heading if i + 1 < len(sections) else ''
            current_chunk_parts = []
            current_chunk_part_headings = []
            continue

        # 用算术估算合并长度，避免在循环内拼接临时字符串（O(n) → O(1)）
        # 等价于 len('\n'.join(current_chunk_parts + [section_text]))，但无列表和字符串分配
        test_len = len('\n'.join(current_chunk_parts)) + 1 + len(section_text)

        if not current_chunk_parts:
            current_chunk_parts = [section_text]
            current_chunk_part_headings = [section.heading if section.heading else '']
            current_heading = section.heading if section.heading else ''
            chunk_start_idx = len(chunks)
        elif test_len <= max_chars:
            current_chunk_parts.append(section_text)
            current_chunk_part_headings.append(section.heading if section.heading else '')
        else:
            if len(current_chunk_parts) == 1:
                chunks.append(flush_chunk(current_chunk_parts, current_heading, chunk_start_idx))
                current_chunk_parts = [section_text]
                current_chunk_part_headings = [section.heading if section.heading else '']
                current_heading = section.heading if section.heading else ''
                chunk_start_idx = len(chunks)
            else:
                chunks.append(flush_chunk(current_chunk_parts, current_heading, chunk_start_idx))

                overlap_text = ''
                section_heading = section.heading if section.heading else ''
                # overlap 不跨标题边界：只有新 section 与前一个 part 同属一个 heading 时才取 overlap
                if overlap > 0 and current_chunk_part_headings and current_chunk_part_headings[-1] == section_heading:
                    overlap_chars = []
                    char_count = 0
                    for part, part_heading in zip(reversed(current_chunk_parts), reversed(current_chunk_part_headings)):
                        if part_heading != section_heading:
                            break
                        for line in reversed(part.splitlines()):
                            overlap_chars.append(line)
                            char_count += len(line)
                            if char_count >= overlap:
                                break
                        if char_count >= overlap:
                            break
                    overlap_text = '\n'.join(reversed(overlap_chars))

                current_chunk_parts = [overlap_text, section_text] if overlap_text else [section_text]
                current_chunk_part_headings = [section_heading, section_heading] if overlap_text else [section_heading]
                current_heading = section.heading if section.heading else ''
                chunk_start_idx = len(chunks)

    if current_chunk_parts:
        chunks.append(flush_chunk(current_chunk_parts, current_heading, chunk_start_idx))

    for i, chunk in enumerate(chunks):
        chunk.chunk_index = i

    return chunks


def _split_by_headings(text: str) -> list[Section]:
    """按 Markdown 任意级别标题（#~######）将正文拆分为 Section 列表。"""
    lines = text.splitlines()
    sections: list[Section] = []
    current_heading = ''
    current_level = 0
    current_lines: list[str] = []

    heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$')

    for line in lines:
        m = heading_pattern.match(line)
        if m:
            if current_lines or current_heading:
                sections.append(Section(current_heading, current_level, '\n'.join(current_lines)))
            current_heading = m.group(2).strip()
            current_level = len(m.group(1))
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines or current_heading:
        sections.append(Section(current_heading, current_level, '\n'.join(current_lines)))

    return sections


def _split_long_section(section_text: str, heading: str, article_id: str, parsed: ParsedArticle, config: Settings, start_idx: int, overlap_text: str = '') -> list[ChunkMeta]:
    """将超过 max_chars 的 section 按段落进一步切分，段落间保留 overlap。"""
    max_chars = config.CHUNK_TARGET_MAX_CHARS
    overlap = config.CHUNK_OVERLAP

    paragraphs = re.split(r'\n\s*\n', section_text)
    chunks: list[ChunkMeta] = []
    current_parts: list[str] = []

    if overlap_text:
        current_parts = [overlap_text]

    def flush(idx: int) -> ChunkMeta:
        text = '\n'.join(current_parts).strip()
        return ChunkMeta(
            chunk_id=_make_chunk_id(article_id, parsed.content_hash, idx),
            article_id=article_id,
            chunk_index=idx,
            nearest_heading=heading,
            text=text,
            source_rel_path=parsed.source_rel_path,
            title=parsed.title,
            content_hash=parsed.content_hash,
            embedding_model=config.EMBEDDING_MODEL,
            embedding_dimension=0,
        )

    char_count = sum(len(p) for p in current_parts) + (len(overlap_text) if overlap_text else 0)

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_len = len(para)

        if char_count + para_len <= max_chars:
            current_parts.append(para)
            char_count += para_len
        else:
            if current_parts:
                chunks.append(flush(start_idx + len(chunks)))
                current_parts = []
                char_count = 0

                if overlap > 0 and chunks:
                    last_chunk_text = chunks[-1].text
                    overlap_chars = []
                    char_acc = 0
                    for line in reversed(last_chunk_text.splitlines()):
                        overlap_chars.append(line)
                        char_acc += len(line)
                        if char_acc >= overlap:
                            break
                    overlap_content = '\n'.join(reversed(overlap_chars))
                    current_parts = [overlap_content]
                    char_count = len(overlap_content)

            if para_len > max_chars:
                sub_chunks = _split_paragraph(para, heading, article_id, parsed, config, start_idx + len(chunks))
                chunks.extend(sub_chunks)
            else:
                current_parts.append(para)
                char_count = sum(len(p) for p in current_parts)

    if current_parts:
        chunks.append(flush(start_idx + len(chunks)))

    return chunks


def _split_paragraph(para: str, heading: str, article_id: str, parsed: ParsedArticle, config: Settings, idx: int) -> list[ChunkMeta]:
    """将超过 max_chars 的单段落按行或句子拆分，保证 embedding 不截断。"""
    max_chars = config.CHUNK_TARGET_MAX_CHARS

    chunks: list[ChunkMeta] = []

    if len(para) <= max_chars:
        return [ChunkMeta(
            chunk_id=_make_chunk_id(article_id, parsed.content_hash, idx),
            article_id=article_id,
            chunk_index=idx,
            nearest_heading=heading,
            text=para,
            source_rel_path=parsed.source_rel_path,
            title=parsed.title,
            content_hash=parsed.content_hash,
            embedding_model=config.EMBEDDING_MODEL,
            embedding_dimension=0,
        )]

    lines = para.splitlines()
    current_lines: list[str] = []
    current_chars = 0

    def make_chunk(text: str, chunk_idx: int) -> ChunkMeta:
        return ChunkMeta(
            chunk_id=_make_chunk_id(article_id, parsed.content_hash, chunk_idx),
            article_id=article_id,
            chunk_index=chunk_idx,
            nearest_heading=heading,
            text=text,
            source_rel_path=parsed.source_rel_path,
            title=parsed.title,
            content_hash=parsed.content_hash,
            embedding_model=config.EMBEDDING_MODEL,
            embedding_dimension=0,
        )

    if len(lines) <= 1:
        sentences = re.split(r'(?<=[。！？.!?])', para)
        current_sentence = ''
        for sent in sentences:
            if len(current_sentence) + len(sent) <= max_chars:
                current_sentence += sent
            else:
                if current_sentence:
                    chunks.append(make_chunk(current_sentence.strip(), idx + len(chunks)))
                if len(sent) > max_chars:
                    for i in range(0, len(sent), max_chars):
                        chunks.append(make_chunk(sent[i:i + max_chars].strip(), idx + len(chunks)))
                    current_sentence = ''
                else:
                    current_sentence = sent
        if current_sentence.strip():
            chunks.append(make_chunk(current_sentence.strip(), idx + len(chunks)))
        return chunks

    for line in lines:
        line_len = len(line)
        if current_chars + line_len > max_chars and current_lines:
            chunks.append(make_chunk('\n'.join(current_lines), idx + len(chunks)))
            current_lines = [line]
            current_chars = line_len
        else:
            current_lines.append(line)
            current_chars += line_len

    if current_lines:
        chunks.append(make_chunk('\n'.join(current_lines), idx + len(chunks)))

    return chunks
