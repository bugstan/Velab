#!/usr/bin/env python3
"""
批量 Embedding 预计算脚本

将 Jira 工单和技术文档通过 OpenAI Embedding API 向量化，
结果序列化到 data/indexes/vector/ 目录，供运行时直接加载。

用法（在 backend/ 目录下执行）：
    source venv/bin/activate
    PYTHONPATH=. python scripts/ingest_embeddings.py

依赖：
    - backend/.env 中配置 OPENAI_API_KEY（场景 B）或 LITELLM_API_KEY（场景 A）
    - data/jira_mock/tickets.json
    - data/docs/index.json
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

# 保证 import 路径正确（从 backend/ 目录运行）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from config import settings
from services.vector_search import VectorSearchService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INDEX_DIR = DATA_DIR / settings.VECTOR_INDEX_DIR


async def ingest_jira(svc: VectorSearchService) -> int:
    """向量化 Jira 工单，保存到 jira_tickets.json。"""
    path = DATA_DIR / "jira_mock" / "tickets.json"
    if not path.exists():
        log.warning("tickets.json 不存在，跳过 Jira 向量化")
        return 0

    tickets: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    log.info("开始向量化 %d 条 Jira 工单 ...", len(tickets))

    docs = []
    for t in tickets:
        text = (
            f"{t.get('key', '')} {t.get('summary', '')} "
            f"{t.get('description', '')} {t.get('resolution', '')}"
        )
        docs.append({"text": text, "metadata": t})

    await svc._index_with_embeddings(docs, "text")
    out_path = INDEX_DIR / "jira_tickets.json"
    saved = svc.save_embed_index(out_path)
    log.info("✅ Jira 工单：向量化 %d 条，已保存到 %s", saved, out_path)
    return saved


async def ingest_docs(svc: VectorSearchService) -> int:
    """向量化技术文档，保存到 tech_docs.json。"""
    path = DATA_DIR / "docs" / "index.json"
    if not path.exists():
        log.warning("docs/index.json 不存在，跳过文档向量化")
        return 0

    documents: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    log.info("开始向量化 %d 份技术文档 ...", len(documents))

    docs = []
    for d in documents:
        text = f"{d.get('title', '')} {d.get('excerpt', '')} {d.get('content', '')}"
        docs.append({"text": text, "metadata": d})

    await svc._index_with_embeddings(docs, "text")
    out_path = INDEX_DIR / "tech_docs.json"
    saved = svc.save_embed_index(out_path)
    log.info("✅ 技术文档：向量化 %d 份，已保存到 %s", saved, out_path)
    return saved


async def main() -> None:
    if not (settings.OPENAI_API_KEY or settings.LITELLM_API_KEY):
        log.error("未找到 OPENAI_API_KEY / LITELLM_API_KEY，无法调用 Embedding API")
        sys.exit(1)

    log.info("=== FOTA 向量化批量入库开始 ===")
    log.info("Embedding 索引输出目录: %s", INDEX_DIR)

    svc = VectorSearchService(use_embeddings=True)

    jira_count = await ingest_jira(svc)
    # 每次 ingest 会重置 _embed_vectors，需要新实例
    svc2 = VectorSearchService(use_embeddings=True)
    docs_count = await ingest_docs(svc2)

    log.info("=== 完成 ===  Jira %d 条 + 文档 %d 份已向量化", jira_count, docs_count)
    log.info("下次启动时设置 AGENTS_USE_EMBEDDINGS=true 以启用 embedding 检索")


if __name__ == "__main__":
    asyncio.run(main())
