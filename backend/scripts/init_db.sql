-- FOTA 数据库初始化脚本

-- 创建案件元数据表
CREATE TABLE IF NOT EXISTS cases (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(100) UNIQUE NOT NULL,
    vin VARCHAR(17),
    vehicle_model VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50),
    metadata JSONB
);

-- 创建标准事件表
CREATE TABLE IF NOT EXISTS standard_events (
    id SERIAL PRIMARY KEY,
    event_code VARCHAR(50) UNIQUE NOT NULL,
    event_name VARCHAR(200),
    description TEXT,
    category VARCHAR(100),
    severity VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建向量索引表（用于语义缓存）
CREATE TABLE IF NOT EXISTS semantic_cache (
    id SERIAL PRIMARY KEY,
    query_hash VARCHAR(64) UNIQUE NOT NULL,
    query_text TEXT NOT NULL,
    query_embedding vector(1536),
    response_text TEXT,
    cache_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    hit_count INTEGER DEFAULT 0
);

-- 创建向量相似度搜索索引
CREATE INDEX IF NOT EXISTS semantic_cache_embedding_idx 
ON semantic_cache USING ivfflat (query_embedding vector_cosine_ops)
WITH (lists = 100);

-- 创建知识库向量表
CREATE TABLE IF NOT EXISTS knowledge_vectors (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(50),
    source_id VARCHAR(200),
    content TEXT,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建知识库向量索引
CREATE INDEX IF NOT EXISTS knowledge_vectors_embedding_idx 
ON knowledge_vectors USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 创建索引以提升查询性能
CREATE INDEX IF NOT EXISTS cases_case_id_idx ON cases(case_id);
CREATE INDEX IF NOT EXISTS cases_vin_idx ON cases(vin);
CREATE INDEX IF NOT EXISTS cases_created_at_idx ON cases(created_at);
CREATE INDEX IF NOT EXISTS semantic_cache_expires_at_idx ON semantic_cache(expires_at);
CREATE INDEX IF NOT EXISTS knowledge_vectors_source_idx ON knowledge_vectors(source_type, source_id);
