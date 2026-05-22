from __future__ import annotations

from mooomoocatrag.models import ChatResponse, IndexManifest


def handle_list(query: str, manifest: IndexManifest) -> ChatResponse:
    articles = [
        entry
        for entry in manifest.articles.values()
        if not entry.get("deleted")
    ]
    if not articles:
        return ChatResponse(
            answer="猫笔刀文章库目前为空。",
            citations=[],
            retrieved_count=0,
            intent="list",
        )

    lines = ["以下是猫笔刀文章库中的文章列表：\n"]
    for i, entry in enumerate(articles, 1):
        title = entry.get("title", "未知标题")
        path = entry.get("source_rel_path", "")
        lines.append(f"{i}. {title}（{path}）")

    return ChatResponse(
        answer="\n".join(lines),
        citations=[],
        retrieved_count=len(articles),
        intent="list",
    )
