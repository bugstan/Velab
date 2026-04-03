-- ============================================================================
-- Velab FOTA 诊断系统 - 数据库种子数据
-- ============================================================================
-- 用途：初始化 FOTA 阶段定义、标准事件字典和默认配置项
-- 使用：psql -U velab_user -d velab_db -f seed_data.sql
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. FOTA 阶段定义表
-- ============================================================================
CREATE TABLE IF NOT EXISTS fota_stages (
    id SERIAL PRIMARY KEY,
    stage_name VARCHAR(50) NOT NULL UNIQUE,
    stage_code VARCHAR(20) NOT NULL UNIQUE,
    description TEXT,
    sequence_order INTEGER NOT NULL,
    is_critical BOOLEAN DEFAULT false,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 插入 FOTA 标准阶段
INSERT INTO fota_stages (stage_name, stage_code, description, sequence_order, is_critical) VALUES
    ('下载阶段', 'DOWNLOAD', 'OTA 包下载过程', 1, true),
    ('校验阶段', 'VERIFY', '下载包完整性和签名校验', 2, true),
    ('刷写阶段', 'FLASH', '固件刷写到目标分区', 3, true),
    ('重启阶段', 'REBOOT', '系统重启并切换分区', 4, true),
    ('验证阶段', 'VALIDATE', '升级后功能验证', 5, true),
    ('回滚阶段', 'ROLLBACK', '升级失败后回滚', 6, false),
    ('完成阶段', 'COMPLETE', 'OTA 流程完成', 7, false)
ON CONFLICT (stage_code) DO NOTHING;

-- ============================================================================
-- 2. 标准事件字典表
-- ============================================================================
CREATE TABLE IF NOT EXISTS event_dictionary (
    id SERIAL PRIMARY KEY,
    event_code VARCHAR(50) NOT NULL UNIQUE,
    event_name VARCHAR(100) NOT NULL,
    stage_code VARCHAR(20) REFERENCES fota_stages(stage_code),
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    description TEXT,
    suggested_action TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 插入标准事件
INSERT INTO event_dictionary (event_code, event_name, stage_code, severity, description, suggested_action) VALUES
    -- 下载阶段事件
    ('DOWNLOAD_START', '开始下载', 'DOWNLOAD', 'INFO', 'OTA 包下载开始', NULL),
    ('DOWNLOAD_PROGRESS', '下载进度', 'DOWNLOAD', 'INFO', 'OTA 包下载进度更新', NULL),
    ('DOWNLOAD_COMPLETE', '下载完成', 'DOWNLOAD', 'INFO', 'OTA 包下载成功完成', NULL),
    ('DOWNLOAD_NETWORK_ERROR', '网络错误', 'DOWNLOAD', 'ERROR', '下载过程中网络连接失败', '检查网络连接，重试下载'),
    ('DOWNLOAD_TIMEOUT', '下载超时', 'DOWNLOAD', 'ERROR', '下载超过预设时间限制', '检查网络速度，增加超时时间'),
    ('DOWNLOAD_DISK_FULL', '磁盘空间不足', 'DOWNLOAD', 'CRITICAL', '目标存储空间不足', '清理磁盘空间后重试'),
    
    -- 校验阶段事件
    ('VERIFY_START', '开始校验', 'VERIFY', 'INFO', '开始校验 OTA 包', NULL),
    ('VERIFY_CHECKSUM_OK', '校验和通过', 'VERIFY', 'INFO', 'OTA 包校验和验证通过', NULL),
    ('VERIFY_SIGNATURE_OK', '签名验证通过', 'VERIFY', 'INFO', 'OTA 包数字签名验证通过', NULL),
    ('VERIFY_CHECKSUM_FAIL', '校验和失败', 'VERIFY', 'CRITICAL', 'OTA 包校验和不匹配', '重新下载 OTA 包'),
    ('VERIFY_SIGNATURE_FAIL', '签名验证失败', 'VERIFY', 'CRITICAL', 'OTA 包签名验证失败', '确认 OTA 包来源，重新下载'),
    ('VERIFY_CORRUPTED', '文件损坏', 'VERIFY', 'CRITICAL', 'OTA 包文件损坏', '重新下载 OTA 包'),
    
    -- 刷写阶段事件
    ('FLASH_START', '开始刷写', 'FLASH', 'INFO', '开始刷写固件', NULL),
    ('FLASH_PROGRESS', '刷写进度', 'FLASH', 'INFO', '固件刷写进度更新', NULL),
    ('FLASH_COMPLETE', '刷写完成', 'FLASH', 'INFO', '固件刷写成功完成', NULL),
    ('FLASH_WRITE_ERROR', '写入错误', 'FLASH', 'CRITICAL', '固件写入失败', '检查存储设备状态'),
    ('FLASH_PARTITION_ERROR', '分区错误', 'FLASH', 'CRITICAL', '目标分区不可用', '检查分区表配置'),
    ('FLASH_INSUFFICIENT_SPACE', '空间不足', 'FLASH', 'CRITICAL', '目标分区空间不足', '检查固件大小和分区配置'),
    
    -- 重启阶段事件
    ('REBOOT_START', '开始重启', 'REBOOT', 'INFO', '系统准备重启', NULL),
    ('REBOOT_COMPLETE', '重启完成', 'REBOOT', 'INFO', '系统重启成功', NULL),
    ('REBOOT_TIMEOUT', '重启超时', 'REBOOT', 'ERROR', '系统重启超时', '手动检查设备状态'),
    ('REBOOT_BOOTLOADER_ERROR', '引导加载器错误', 'REBOOT', 'CRITICAL', '引导加载器启动失败', '检查 bootloader 配置'),
    
    -- 验证阶段事件
    ('VALIDATE_START', '开始验证', 'VALIDATE', 'INFO', '开始升级后验证', NULL),
    ('VALIDATE_VERSION_OK', '版本验证通过', 'VALIDATE', 'INFO', '固件版本验证通过', NULL),
    ('VALIDATE_FUNCTION_OK', '功能验证通过', 'VALIDATE', 'INFO', '关键功能验证通过', NULL),
    ('VALIDATE_VERSION_MISMATCH', '版本不匹配', 'VALIDATE', 'ERROR', '实际版本与预期不符', '触发回滚流程'),
    ('VALIDATE_FUNCTION_FAIL', '功能验证失败', 'VALIDATE', 'ERROR', '关键功能验证失败', '触发回滚流程'),
    
    -- 回滚阶段事件
    ('ROLLBACK_START', '开始回滚', 'ROLLBACK', 'WARNING', '开始回滚到旧版本', NULL),
    ('ROLLBACK_COMPLETE', '回滚完成', 'ROLLBACK', 'WARNING', '成功回滚到旧版本', NULL),
    ('ROLLBACK_FAIL', '回滚失败', 'ROLLBACK', 'CRITICAL', '回滚过程失败', '需要人工介入恢复'),
    
    -- 完成阶段事件
    ('COMPLETE_SUCCESS', 'OTA 成功', 'COMPLETE', 'INFO', 'OTA 升级成功完成', NULL),
    ('COMPLETE_FAIL', 'OTA 失败', 'COMPLETE', 'ERROR', 'OTA 升级失败', '查看详细日志分析原因')
ON CONFLICT (event_code) DO NOTHING;

-- ============================================================================
-- 3. 系统配置表
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) NOT NULL UNIQUE,
    config_value TEXT NOT NULL,
    config_type VARCHAR(20) NOT NULL CHECK (config_type IN ('STRING', 'INTEGER', 'BOOLEAN', 'JSON')),
    description TEXT,
    is_editable BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 插入默认配置
INSERT INTO system_config (config_key, config_value, config_type, description, is_editable) VALUES
    -- 日志处理配置
    ('log.retention_days', '90', 'INTEGER', '日志保留天数', true),
    ('log.batch_size', '1000', 'INTEGER', '日志批处理大小', true),
    ('log.processing_interval', '300', 'INTEGER', '日志处理间隔（秒）', true),
    
    -- FOTA 配置
    ('fota.max_retry_count', '3', 'INTEGER', 'FOTA 最大重试次数', true),
    ('fota.download_timeout', '3600', 'INTEGER', '下载超时时间（秒）', true),
    ('fota.verify_timeout', '300', 'INTEGER', '校验超时时间（秒）', true),
    ('fota.flash_timeout', '1800', 'INTEGER', '刷写超时时间（秒）', true),
    
    -- AI 分析配置
    ('ai.model_name', 'gpt-4', 'STRING', '默认 AI 模型', true),
    ('ai.max_tokens', '4096', 'INTEGER', 'AI 响应最大 token 数', true),
    ('ai.temperature', '0.7', 'STRING', 'AI 温度参数', true),
    ('ai.enable_chain_log', 'true', 'BOOLEAN', '是否启用思维链日志', true),
    
    -- 告警配置
    ('alert.enable_email', 'false', 'BOOLEAN', '是否启用邮件告警', true),
    ('alert.enable_webhook', 'false', 'BOOLEAN', '是否启用 Webhook 告警', true),
    ('alert.critical_threshold', '5', 'INTEGER', '严重错误告警阈值', true),
    
    -- 系统配置
    ('system.version', '1.0.0', 'STRING', '系统版本', false),
    ('system.environment', 'development', 'STRING', '运行环境', true),
    ('system.debug_mode', 'true', 'BOOLEAN', '调试模式', true)
ON CONFLICT (config_key) DO NOTHING;

-- ============================================================================
-- 4. 创建索引
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_event_stage ON event_dictionary(stage_code);
CREATE INDEX IF NOT EXISTS idx_event_severity ON event_dictionary(severity);
CREATE INDEX IF NOT EXISTS idx_config_key ON system_config(config_key);

-- ============================================================================
-- 5. 创建更新时间触发器
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_system_config_updated_at
    BEFORE UPDATE ON system_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMIT;

-- ============================================================================
-- 验证数据插入
-- ============================================================================
SELECT 'FOTA 阶段数量: ' || COUNT(*) FROM fota_stages;
SELECT '事件字典数量: ' || COUNT(*) FROM event_dictionary;
SELECT '系统配置数量: ' || COUNT(*) FROM system_config;

-- ============================================================================
-- 完成
-- ============================================================================
\echo '✓ 种子数据初始化完成'
