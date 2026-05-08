from __future__ import annotations

import shutil
from pathlib import Path

import typer

from mooomoocatrag.config import Settings, get_settings, setup_logging
from mooomoocatrag.ingest.chunker import chunk_article
from mooomoocatrag.ingest.indexer import (
    article_to_manifest_entry,
    build_empty_manifest,
    find_deleted_article_ids,
    load_manifest,
    save_manifest,
)
from mooomoocatrag.ingest.parser import parse_article
from mooomoocatrag.ingest.scanner import scan_articles
from mooomoocatrag.models import IndexManifest
from mooomoocatrag.rag.chat import chat_turn
from mooomoocatrag.rag.embeddings import embed_texts
from mooomoocatrag.rag.retriever import retrieve
from mooomoocatrag.rag.vector_store import add_chunks, check_consistency, delete_chunks

app = typer.Typer(name="mooomoocatrag", help="猫笔刀文章 RAG Agent")


@app.command()
def ingest(
    rebuild: bool = typer.Option(False, "--rebuild", help="清空旧索引并重建"),
    force: bool = typer.Option(False, "--force", help="跳过确认直接重建"),
) -> None:
    """导入和索引文章。"""
    settings = get_settings()
    setup_logging()
    source_root = _validated_source_root(settings)
    _require_embedding_config(settings)

    if rebuild:
        _confirm_rebuild(force)
        _clear_index_data(settings)

    scanned_articles = scan_articles(str(source_root))
    if not scanned_articles:
        _fail(f"文章目录中没有找到 .md 或 .txt 文件：{source_root}")

    manifest = load_manifest(settings.DATA_DIR)
    if rebuild or not manifest.articles or not manifest.embedding_model:
        manifest = build_empty_manifest(settings, str(source_root))
    else:
        check_consistency(settings, manifest)

    stats = {
        "skipped": 0,
        "added": 0,
        "updated": 0,
        "deleted": 0,
        "chunks": 0,
        "warnings": 0,
    }

    current_article_ids = {article.article_id for article in scanned_articles}
    for deleted_id in find_deleted_article_ids(manifest, current_article_ids):
        deleted_entry = manifest.articles.get(deleted_id, {})
        try:
            delete_chunks(deleted_entry.get("chunk_ids", []), settings)
        except Exception as exc:  # pragma: no cover - defensive integration path
            stats["warnings"] += 1
            typer.secho(f"删除旧 chunk 失败：{deleted_id}: {exc}", fg=typer.colors.YELLOW)
        manifest.articles.pop(deleted_id, None)
        stats["deleted"] += 1

    for article in scanned_articles:
        existing_entry = manifest.articles.get(article.article_id)
        if existing_entry and existing_entry.get("content_hash") == article.content_hash:
            stats["skipped"] += 1
            continue

        parsed = parse_article(
            article.source_path,
            article.file_type,
            source_root=str(source_root),
            source_rel_path=article.source_rel_path,
        )
        chunks = chunk_article(parsed, article.article_id, settings)
        vectors = embed_texts([chunk.text for chunk in chunks], settings)

        embedding_dimension = len(vectors[0]) if vectors else manifest.embedding_dimension
        if manifest.embedding_dimension and embedding_dimension:
            check_consistency(settings, manifest, embedding_dimension=embedding_dimension)
        elif embedding_dimension:
            manifest.embedding_dimension = embedding_dimension

        for chunk in chunks:
            chunk.embedding_dimension = embedding_dimension

        add_chunks(chunks, vectors, settings)

        if existing_entry:
            old_chunk_ids = existing_entry.get("chunk_ids", [])
            try:
                delete_chunks(old_chunk_ids, settings)
            except Exception as exc:  # pragma: no cover - defensive integration path
                stats["warnings"] += 1
                typer.secho(
                    f"删除旧 chunk 失败：{article.source_rel_path}: {exc}",
                    fg=typer.colors.YELLOW,
                )
            stats["updated"] += 1
        else:
            stats["added"] += 1

        manifest.articles[article.article_id] = article_to_manifest_entry(
            article,
            chunks,
            existing_entry=existing_entry,
        )
        stats["chunks"] += len(chunks)

    save_manifest(manifest, settings.DATA_DIR)

    typer.echo(
        "索引完成："
        f"扫描 {len(scanned_articles)} 个文件，"
        f"跳过 {stats['skipped']}（未变化），"
        f"新增 {stats['added']}，"
        f"更新 {stats['updated']}，"
        f"删除 {stats['deleted']}，"
        f"共 {stats['chunks']} 个 chunks，"
        f"{stats['warnings']} 个警告"
    )


@app.command()
def search(
    query: str = typer.Argument(..., help="搜索问题"),
) -> None:
    """测试检索。"""
    settings = get_settings()
    setup_logging()
    _require_embedding_config(settings)
    manifest = _load_ready_manifest(settings)
    check_consistency(settings, manifest)

    results = retrieve(query, settings, manifest)
    if not results:
        typer.echo("没有找到足够相关的文章片段。")
        return

    typer.echo("---")
    for index, result in enumerate(results, 1):
        heading = result.chunk.nearest_heading or "无"
        preview = _preview(result.chunk.text)
        typer.echo(
            f"[{index}] 相似度: {result.similarity:.2f} | "
            f"{result.chunk.title} | {result.chunk.source_rel_path} | "
            f"chunk {result.chunk.chunk_index} | 小标题：{heading}"
        )
        typer.echo(f"  {preview}")
        typer.echo("")
    typer.echo("---")
    typer.echo(f"共 {len(results)} 个结果")


@app.command()
def chat() -> None:
    """进入对话模式。"""
    settings = get_settings()
    setup_logging()
    _require_embedding_config(settings)
    _require_llm_config(settings)
    manifest = _load_ready_manifest(settings)
    check_consistency(settings, manifest)

    history: list[dict] = []
    question_count = 0
    referenced_citations: set[str] = set()

    while True:
        try:
            query = input("你> ").strip()
        except EOFError:
            typer.echo("")
            break

        if not query:
            continue
        if query in {"/exit", "/quit"}:
            break

        response = chat_turn(query, history, settings, manifest)
        question_count += 1
        typer.echo(response.answer)

        if response.citations:
            typer.echo("引用：")
            for citation in response.citations:
                referenced_citations.add(citation)
                typer.echo(citation)

        history.append({"role": "user", "content": query})
        history.append({"role": "assistant", "content": response.answer})

    typer.echo(
        f"会话结束：共提问 {question_count} 次，"
        f"引用 {len(referenced_citations)} 篇文章"
    )


def _validated_source_root(settings: Settings) -> Path:
    if not settings.ARTICLE_SOURCE_DIR:
        _fail("缺少配置 ARTICLE_SOURCE_DIR，请在 .env 中填写文章目录。")

    source_root = Path(settings.ARTICLE_SOURCE_DIR).expanduser().resolve()
    if not source_root.exists():
        _fail(f"文章目录不存在：{source_root}")
    if not source_root.is_dir():
        _fail(f"ARTICLE_SOURCE_DIR 不是目录：{source_root}")
    return source_root


def _require_embedding_config(settings: Settings) -> None:
    missing = []
    if not settings.effective_embedding_base_url:
        missing.append("OPENAI_COMPAT_BASE_URL 或 EMBEDDING_BASE_URL")
    if not settings.effective_embedding_api_key:
        missing.append("OPENAI_COMPAT_API_KEY 或 EMBEDDING_API_KEY")
    if not settings.EMBEDDING_MODEL:
        missing.append("EMBEDDING_MODEL")
    if missing:
        _fail("缺少 Embedding 配置：" + "、".join(missing))


def _require_llm_config(settings: Settings) -> None:
    missing = []
    if not settings.effective_llm_base_url:
        missing.append("OPENAI_COMPAT_BASE_URL 或 LLM_BASE_URL")
    if not settings.effective_llm_api_key:
        missing.append("OPENAI_COMPAT_API_KEY 或 LLM_API_KEY")
    if not settings.LLM_MODEL:
        missing.append("LLM_MODEL")
    if missing:
        _fail("缺少 LLM 配置：" + "、".join(missing))


def _load_ready_manifest(settings: Settings) -> IndexManifest:
    manifest = load_manifest(settings.DATA_DIR)
    if not manifest.articles:
        _fail("索引为空，请先运行：mooomoocatrag ingest")
    return manifest


def _confirm_rebuild(force: bool) -> None:
    if force:
        return
    confirmed = typer.confirm("确认清空旧索引并重建？")
    if not confirmed:
        raise typer.Exit(code=1)


def _clear_index_data(settings: Settings) -> None:
    chroma_dir = Path(settings.chroma_dir)
    manifest_path = Path(settings.manifest_path)
    if chroma_dir.exists():
        shutil.rmtree(chroma_dir)
    if manifest_path.exists():
        manifest_path.unlink()


def _preview(text: str, max_chars: int = 200) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars] + "..."


def _fail(message: str) -> None:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
