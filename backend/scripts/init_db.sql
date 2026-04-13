-- FOTA 数据库初始化脚本

-- 创建案件元数据表
CREATE TABLE IF NOT EXISTS cases (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(100) UNIQUE NOT NULL,
    vin VARCHAR(17),
    vehicle_model VARCHAR(100),
    issue_description VARCHAR(500),
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

-- ============================================================
-- P0 任务补充：离线数据预处理管线所需的核心表
-- ============================================================

-- 1. 原始日志文件元数据表
CREATE TABLE IF NOT EXISTS raw_log_files (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(100) NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    file_id VARCHAR(128) UNIQUE NOT NULL,
    original_filename VARCHAR(500) NOT NULL,
    file_size BIGINT NOT NULL,
    mime_type VARCHAR(100),
    source_type VARCHAR(32) NOT NULL,  -- android / kernel / fota / dlt / mcu / ibdu / vehicle_signal
    storage_path TEXT NOT NULL,  -- MinIO 对象存储路径
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    parse_status VARCHAR(32) DEFAULT 'PENDING',  -- PENDING / PARSING / PARSED / FAILED
    parse_started_at TIMESTAMP,
    parse_completed_at TIMESTAMP,
    parse_error TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 诊断事件详情表（解析后的结构化事件）
CREATE TABLE IF NOT EXISTS diagnosis_events (
    id BIGSERIAL PRIMARY KEY,
    case_id VARCHAR(100) NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    file_id VARCHAR(128) NOT NULL REFERENCES raw_log_files(file_id) ON DELETE CASCADE,
    source_type VARCHAR(32) NOT NULL,
    
    -- 时间戳字段
    original_ts TIMESTAMP,  -- 原始日志中的时间戳
    normalized_ts TIMESTAMP,  -- 时间对齐后的标准化时间戳
    clock_confidence FLOAT DEFAULT 1.0,  -- 时间对齐置信度 (0.0-1.0)
    
    -- 事件内容
    event_type VARCHAR(100),  -- ERROR / WARNING / INFO / STATE_CHANGE / FOTA_STAGE
    module VARCHAR(100),
    level VARCHAR(20),  -- ERROR / WARN / INFO / DEBUG
    message TEXT NOT NULL,
    
    -- 原始日志回溯
    raw_line_number INT,
    raw_snippet TEXT,  -- 原始日志片段（前后各3行）
    
    -- 结构化解析字段（因日志类型而异）
    parsed_fields JSONB DEFAULT '{}',
    
    -- 元数据
    parser_name VARCHAR(64),
    parser_version VARCHAR(32) DEFAULT '1.0.0',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 索引优化
    CONSTRAINT diagnosis_events_case_file_idx UNIQUE (case_id, file_id, raw_line_number)
);

-- 3. 已确认诊断缓存表（用于反馈闭环和长期记忆）
CREATE TABLE IF NOT EXISTS confirmed_diagnosis (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(100) NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
    
    -- 诊断结果
    root_cause TEXT NOT NULL,
    confidence FLOAT NOT NULL,
    recommendations TEXT[],
    
    -- 工程师确认信息
    confirmed_by VARCHAR(100),  -- 工程师ID或邮箱
    confirmed_at TIMESTAMP NOT NULL,
    confirmation_status VARCHAR(20) NOT NULL,  -- CONFIRMED / REJECTED / PARTIAL
    engineer_notes TEXT,
    
    -- 关联证据
    evidence_log_ids BIGINT[],  -- 关联的 diagnosis_events.id
    evidence_jira_ids VARCHAR(200)[],  -- 关联的 Jira Issue ID
    evidence_doc_ids VARCHAR(200)[],  -- 关联的文档 chunk ID
    
    -- 向量化（用于相似案例检索）
    diagnosis_embedding vector(1536),
    
    -- 元数据
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 索引优化
-- ============================================================

-- 原有索引
CREATE INDEX IF NOT EXISTS cases_case_id_idx ON cases(case_id);
CREATE INDEX IF NOT EXISTS cases_vin_idx ON cases(vin);
CREATE INDEX IF NOT EXISTS cases_created_at_idx ON cases(created_at);
CREATE INDEX IF NOT EXISTS semantic_cache_expires_at_idx ON semantic_cache(expires_at);
CREATE INDEX IF NOT EXISTS knowledge_vectors_source_idx ON knowledge_vectors(source_type, source_id);

-- 新增索引：raw_log_files
CREATE INDEX IF NOT EXISTS raw_log_files_case_id_idx ON raw_log_files(case_id);
CREATE INDEX IF NOT EXISTS raw_log_files_file_id_idx ON raw_log_files(file_id);
CREATE INDEX IF NOT EXISTS raw_log_files_parse_status_idx ON raw_log_files(parse_status);
CREATE INDEX IF NOT EXISTS raw_log_files_source_type_idx ON raw_log_files(source_type);

-- 新增索引：diagnosis_events（时间轴查询优化）
CREATE INDEX IF NOT EXISTS diagnosis_events_case_id_idx ON diagnosis_events(case_id);
CREATE INDEX IF NOT EXISTS diagnosis_events_normalized_ts_idx ON diagnosis_events(normalized_ts);
CREATE INDEX IF NOT EXISTS diagnosis_events_event_type_idx ON diagnosis_events(event_type);
CREATE INDEX IF NOT EXISTS diagnosis_events_module_idx ON diagnosis_events(module);
CREATE INDEX IF NOT EXISTS diagnosis_events_case_time_idx ON diagnosis_events(case_id, normalized_ts);
CREATE INDEX IF NOT EXISTS diagnosis_events_case_module_idx ON diagnosis_events(case_id, module);

-- 新增索引：confirmed_diagnosis
CREATE INDEX IF NOT EXISTS confirmed_diagnosis_case_id_idx ON confirmed_diagnosis(case_id);
CREATE INDEX IF NOT EXISTS confirmed_diagnosis_confirmed_at_idx ON confirmed_diagnosis(confirmed_at);
CREATE INDEX IF NOT EXISTS confirmed_diagnosis_status_idx ON confirmed_diagnosis(confirmation_status);

-- 向量相似度搜索索引（confirmed_diagnosis）
CREATE INDEX IF NOT EXISTS confirmed_diagnosis_embedding_idx
ON confirmed_diagnosis USING ivfflat (diagnosis_embedding vector_cosine_ops)
WITH (lists = 100);
