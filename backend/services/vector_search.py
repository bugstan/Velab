"""
向量检索服务 — Jira 工单和文档的语义搜索

两种运行模式：
1. Baseline（无 LLM）：使用 TF-IDF + 余弦相似度做文本匹配
2. Embedding（需 LLM）：使用 embedding 模型生成向量后检索（预留接口）

作者：FOTA 诊断平台团队
创建时间：2026-04-06
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class VectorSearchService:
    """
    向量检索服务

    在没有 embedding model 时，使用 TF-IDF baseline 提供基本的语义匹配能力。
    当 embedding API 可用后，切换到向量余弦相似度检索。
    """

    def __init__(self, use_embeddings: bool = False):
        """
        Args:
            use_embeddings: 是否使用 embedding 模型（需 API Key）
        """
        self.use_embeddings = use_embeddings
        self._idf_cache: Dict[str, float] = {}
        self._doc_vectors: List[Tuple[str, Dict[str, float], Dict[str, Any]]] = []

    # ── 公共接口 ──

    def index_documents(self, documents: List[Dict[str, Any]], text_field: str = "text") -> int:
        """
        索引文档集合

        Args:
            documents: 文档列表，每个文档需包含 text_field 字段
            text_field: 文本字段名

        Returns:
            索引的文档数量
        """
        if self.use_embeddings:
            return self._index_with_embeddings(documents, text_field)
        return self._index_with_tfidf(documents, text_field)

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.1,
    ) -> List[Dict[str, Any]]:
        """
        搜索相关文档

        Args:
            query: 查询文本
            top_k: 返回前 K 个结果
            min_score: 最低相似度阈值

        Returns:
            按相似度降序排列的搜索结果
        """
        if self.use_embeddings:
            return self._search_with_embeddings(query, top_k, min_score)
        return self._search_with_tfidf(query, top_k, min_score)

    def search_jira_issues(
        self,
        query: str,
        tickets: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        搜索 Jira 工单

        Args:
            query: 查询文本
            tickets: 工单列表
            top_k: 返回前 K 个结果

        Returns:
            相关工单列表（含相似度分数）
        """
        # 将工单转为检索文档
        docs = []
        for t in tickets:
            text = f"{t.get('key', '')} {t.get('summary', '')} {t.get('description', '')} {t.get('resolution', '')}"
            docs.append({"text": text, "metadata": t})

        self._index_with_tfidf(docs, "text")
        results = self._search_with_tfidf(query, top_k, min_score=0.05)

        return [
            {**r["metadata"], "similarity_score": r["score"]}
            for r in results
        ]

    def search_documents(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        搜索技术文档

        Args:
            query: 查询文本
            documents: 文档列表
            top_k: 返回前 K 个结果

        Returns:
            相关文档列表（含相似度分数）
        """
        docs = []
        for d in documents:
            text = f"{d.get('title', '')} {d.get('excerpt', '')} {d.get('content', '')}"
            docs.append({"text": text, "metadata": d})

        self._index_with_tfidf(docs, "text")
        results = self._search_with_tfidf(query, top_k, min_score=0.05)

        return [
            {**r["metadata"], "similarity_score": r["score"]}
            for r in results
        ]

    # ── TF-IDF Baseline 实现 ──

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """中英文混合分词"""
        # 英文按单词分割，中文按字/词分割
        text = text.lower()
        # 英文单词
        en_tokens = re.findall(r'[a-z][a-z0-9_\-]*(?:\.[a-z0-9]+)*', text)
        # 中文字符序列（简单的 bigram）
        cn_chars = re.findall(r'[\u4e00-\u9fff]+', text)
        cn_tokens = []
        for segment in cn_chars:
            for i in range(len(segment) - 1):
                cn_tokens.append(segment[i:i+2])
            if len(segment) == 1:
                cn_tokens.append(segment)

        return en_tokens + cn_tokens

    def _compute_tf(self, tokens: List[str]) -> Dict[str, float]:
        """计算词频 (TF)"""
        counter = Counter(tokens)
        total = len(tokens) or 1
        return {term: count / total for term, count in counter.items()}

    def _compute_idf(self, doc_tokens_list: List[List[str]]) -> Dict[str, float]:
        """计算逆文档频率 (IDF)"""
        n_docs = len(doc_tokens_list)
        if n_docs == 0:
            return {}

        df: Dict[str, int] = {}
        for tokens in doc_tokens_list:
            seen = set(tokens)
            for term in seen:
                df[term] = df.get(term, 0) + 1

        return {
            term: math.log((n_docs + 1) / (freq + 1)) + 1
            for term, freq in df.items()
        }

    def _tfidf_vector(self, tf: Dict[str, float], idf: Dict[str, float]) -> Dict[str, float]:
        """计算 TF-IDF 向量"""
        return {term: tf_val * idf.get(term, 1.0) for term, tf_val in tf.items()}

    @staticmethod
    def _cosine_similarity(v1: Dict[str, float], v2: Dict[str, float]) -> float:
        """计算余弦相似度"""
        common_keys = set(v1.keys()) & set(v2.keys())
        if not common_keys:
            return 0.0

        dot_product = sum(v1[k] * v2[k] for k in common_keys)
        norm1 = math.sqrt(sum(v ** 2 for v in v1.values()))
        norm2 = math.sqrt(sum(v ** 2 for v in v2.values()))

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)

    def _index_with_tfidf(self, documents: List[Dict[str, Any]], text_field: str) -> int:
        """使用 TF-IDF 索引文档"""
        self._doc_vectors = []

        all_tokens = []
        for doc in documents:
            tokens = self._tokenize(doc.get(text_field, ""))
            all_tokens.append(tokens)

        self._idf_cache = self._compute_idf(all_tokens)

        for doc, tokens in zip(documents, all_tokens):
            tf = self._compute_tf(tokens)
            tfidf = self._tfidf_vector(tf, self._idf_cache)
            self._doc_vectors.append((doc.get(text_field, "")[:200], tfidf, doc.get("metadata", doc)))

        logger.debug("TF-IDF indexed %d documents", len(self._doc_vectors))
        return len(self._doc_vectors)

    def _search_with_tfidf(
        self, query: str, top_k: int, min_score: float
    ) -> List[Dict[str, Any]]:
        """使用 TF-IDF 搜索"""
        query_tokens = self._tokenize(query)
        query_tf = self._compute_tf(query_tokens)
        query_vec = self._tfidf_vector(query_tf, self._idf_cache)

        scored = []
        for text_preview, doc_vec, metadata in self._doc_vectors:
            score = self._cosine_similarity(query_vec, doc_vec)
            if score >= min_score:
                scored.append({
                    "score": round(score, 4),
                    "text_preview": text_preview,
                    "metadata": metadata,
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    # ── Embedding 实现（预留） ──

    def _index_with_embeddings(self, documents: List[Dict[str, Any]], text_field: str) -> int:
        """使用 embedding 模型索引（需 API Key）"""
        logger.warning("Embedding indexing not yet available, falling back to TF-IDF")
        return self._index_with_tfidf(documents, text_field)

    def _search_with_embeddings(
        self, query: str, top_k: int, min_score: float
    ) -> List[Dict[str, Any]]:
        """使用 embedding 模型搜索（需 API Key）"""
        logger.warning("Embedding search not yet available, falling back to TF-IDF")
        return self._search_with_tfidf(query, top_k, min_score)


# 全局单例
vector_service = VectorSearchService(use_embeddings=False)
