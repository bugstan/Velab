"""
语义缓存服务 — 诊断查询结果缓存

两层缓存策略：
1. 精确哈希匹配 — 基于查询文本 SHA-256 哈希（不需要LLM）
2. 向量相似匹配 — 基于 embedding 余弦相似度（需要LLM，预留接口）

对应数据库表：semantic_cache

作者：FOTA 诊断平台团队
创建时间：2026-04-06
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 默认缓存过期时间（小时）
DEFAULT_TTL_HOURS = 24


class SemanticCacheService:
    """
    语义缓存服务

    提供诊断结果的缓存存取功能：
    - 精确匹配：查询文本哈希完全一致
    - 语义匹配：向量余弦相似度 > 阈值（预留）
    """

    def __init__(self, ttl_hours: int = DEFAULT_TTL_HOURS):
        self.ttl_hours = ttl_hours

    @staticmethod
    def _hash_query(query_text: str, scenario_id: str = "") -> str:
        """生成查询哈希"""
        normalized = query_text.strip().lower()
        content = f"{scenario_id}|{normalized}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_cached_response(
        self,
        db: Session,
        query_text: str,
        scenario_id: str = "",
        cache_type: str = "exact",
    ) -> Optional[Dict[str, Any]]:
        """
        查询缓存

        Args:
            db: 数据库会话
            query_text: 查询文本
            scenario_id: 场景 ID
            cache_type: 缓存类型（exact / semantic）

        Returns:
            缓存的响应数据，未命中返回 None
        """
        query_hash = self._hash_query(query_text, scenario_id)

        result = db.execute(
            text("""
                SELECT id, response_text, cache_type, created_at, expires_at, hit_count
                FROM semantic_cache
                WHERE query_hash = :hash
                  AND cache_type = :cache_type
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"hash": query_hash, "cache_type": cache_type},
        ).fetchone()

        if result is None:
            logger.debug("Cache MISS: hash=%s type=%s", query_hash[:12], cache_type)
            return None

        # 更新命中计数
        db.execute(
            text("UPDATE semantic_cache SET hit_count = hit_count + 1 WHERE id = :id"),
            {"id": result.id},
        )
        db.commit()

        logger.info(
            "Cache HIT: hash=%s type=%s hits=%d",
            query_hash[:12],
            cache_type,
            result.hit_count + 1,
        )

        try:
            return json.loads(result.response_text)
        except (json.JSONDecodeError, TypeError):
            return {"raw_response": result.response_text}

    def set_cached_response(
        self,
        db: Session,
        query_text: str,
        response_data: Dict[str, Any],
        scenario_id: str = "",
        cache_type: str = "exact",
        ttl_hours: Optional[int] = None,
    ) -> str:
        """
        写入缓存

        Args:
            db: 数据库会话
            query_text: 查询文本
            response_data: 要缓存的响应数据
            scenario_id: 场景 ID
            cache_type: 缓存类型
            ttl_hours: 缓存有效期（小时），None 使用默认值

        Returns:
            缓存的查询哈希
        """
        query_hash = self._hash_query(query_text, scenario_id)
        ttl = ttl_hours if ttl_hours is not None else self.ttl_hours
        expires_at = datetime.utcnow() + timedelta(hours=ttl) if ttl > 0 else None

        response_text = json.dumps(response_data, ensure_ascii=False)

        # UPSERT — 相同 hash 更新而不是重复插入
        db.execute(
            text("""
                INSERT INTO semantic_cache (query_hash, query_text, response_text, cache_type, expires_at, hit_count)
                VALUES (:hash, :query, :response, :cache_type, :expires, 0)
                ON CONFLICT (query_hash) DO UPDATE SET
                    response_text = :response,
                    expires_at = :expires,
                    hit_count = 0,
                    created_at = NOW()
            """),
            {
                "hash": query_hash,
                "query": query_text[:2000],
                "response": response_text,
                "cache_type": cache_type,
                "expires": expires_at,
            },
        )
        db.commit()

        logger.info("Cache SET: hash=%s type=%s ttl=%dh", query_hash[:12], cache_type, ttl)
        return query_hash

    def invalidate(
        self,
        db: Session,
        query_text: Optional[str] = None,
        scenario_id: str = "",
        cache_type: Optional[str] = None,
    ) -> int:
        """
        使缓存失效

        Args:
            db: 数据库会话
            query_text: 查询文本（为空则清理所有过期缓存）
            scenario_id: 场景 ID
            cache_type: 缓存类型

        Returns:
            删除的缓存条目数
        """
        if query_text:
            query_hash = self._hash_query(query_text, scenario_id)
            result = db.execute(
                text("DELETE FROM semantic_cache WHERE query_hash = :hash"),
                {"hash": query_hash},
            )
        elif cache_type:
            result = db.execute(
                text("DELETE FROM semantic_cache WHERE cache_type = :type AND expires_at < NOW()"),
                {"type": cache_type},
            )
        else:
            # 清理所有过期缓存
            result = db.execute(
                text("DELETE FROM semantic_cache WHERE expires_at IS NOT NULL AND expires_at < NOW()")
            )

        db.commit()
        deleted = result.rowcount
        logger.info("Cache INVALIDATE: deleted=%d", deleted)
        return deleted

    def get_stats(self, db: Session) -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            dict: 缓存统计
        """
        result = db.execute(
            text("""
                SELECT
                    COUNT(*) as total_entries,
                    SUM(hit_count) as total_hits,
                    COUNT(CASE WHEN expires_at IS NOT NULL AND expires_at < NOW() THEN 1 END) as expired_entries,
                    AVG(hit_count) as avg_hits
                FROM semantic_cache
            """)
        ).fetchone()

        return {
            "total_entries": result.total_entries or 0,
            "total_hits": result.total_hits or 0,
            "expired_entries": result.expired_entries or 0,
            "avg_hits_per_entry": round(float(result.avg_hits or 0), 2),
        }


# 全局单例
cache_service = SemanticCacheService()
