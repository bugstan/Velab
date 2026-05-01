```markdown
# 整车日志分析系统 — 日志分类与时间对齐模块

> 本文档为 Claude Code 的实现指南。读者：负责本模块编码、测试与交付的开发者（含 AI 助手）。
> 本文件即开发契约：所有模块边界、数据模型、接口定义以本文为准；实现细节（私有函数命名等）可在编码阶段微调，但不得违反本文契约。

---

## 0. 文档使用约定

- **【MUST】** 标记的内容为强约束，违反即视为缺陷。
- **【SHOULD】** 标记的内容为推荐做法，可在有充分理由时偏离，但需在 PR 描述中说明。
- **【MAY】** 标记的内容为可选优化。
- 所有外置配置文件路径以 `config/` 为根。
- 所有代码示例为说明用途，**不是**最终落地代码。

---

## 1. 模块定位与目标

### 1.1 上下文

本模块是"整车日志分析系统"的**前置处理层**。
- **上游**：用户上传整车日志压缩包（zip / tar.gz / 7z），内含多控制器混合日志。
- **下游**：故障分析层、可视化层。下游通过本模块提供的接口拿到"按时间段切片的多控制器日志"与"重要事件流"。

### 1.2 目标

1. 接收上传压缩包，**全量保留**所有原始日志文件（即便同名也不覆盖、不合并）。
2. 按控制器分类归档，每个控制器一类。
3. 对二进制日志（如 DLT）解码为可读文本。
4. 以 **tbox 时间为统一时钟源**，计算各控制器到 tbox 的偏移；**不修改原始日志**，对齐结果仅在查询时换算。
5. 处理控制器重启导致的"伪时间戳段"（1970/2000 起的时间戳），将其标注为未同步段，但保留日志行。
6. 单遍预扫描：抽取重要事件、采集锚点、构建文件级时间索引。
7. 重要事件入库；日志行**不入库**，以文件 + 索引方式存储。
8. 提供按统一时间段查询接口，输出全量版与精简版两种格式，支持流式响应。

### 1.3 非目标

- 不在写入阶段修改或改写日志时间戳。
- 不把日志原始行入库。
- 不内置硬编码事件字典——事件规则一律外置为 YAML。
- 不做日志可视化、不做故障判定逻辑（属于下游）。

### 1.4 存储策略总览（强约束）

【MUST】本模块严格区分"磁盘文件"与"数据库"两种持久化方式：

| 数据类别 | 存储位置 | 形态 | 说明 |
|---------|---------|------|------|
| 上传压缩包原始文件 | 磁盘 | 二进制 / 文本（按原样） | 解压后按 `{store_root}/{bundle_id}/{controller}/{file_id}__{original_name}` 落盘；同名**绝不覆盖** |
| 分类 / 解码后的日志 | **磁盘文件** | **可读文本**（UTF-8） | DLT 等二进制源解码后写 `{stored_path}.decoded.log`；其它文本类直接保留原文。**严禁入库** |
| 桶索引 `.idx` | 磁盘 | 紧凑二进制（每记录 24B 定长） | 每个解码后文件一份，按 `bucket_id` 升序 |
| catalog（bundle / file 元数据） | **数据库** | 结构化表（见 §6.6） | 含 `clock_offset`、`unsynced_ranges`、`bucket_index_path` 等 |
| 重要事件 `ImportantEvent` | **数据库** | 结构化表 | 唯一入库的"日志衍生数据"，便于按类型 / 时间窗高速查询 |
| 精简版日志 (slim) | **不存储** | —— | **动态过滤**：查询时按 `slim_rules.yaml` 即时三级判定（`keep_always > drop > pass-through`），不预生成、不落盘、不入库 |
| 处理日志 `_processing.log` | 磁盘 | 文本 | 每 bundle 一份，审计用 |
| 对齐结果 `aligned_ts` | 不持久化 | 查询时计算 | `aligned_ts = raw_ts + offset`，offset 来自 catalog |

【MUST】**禁止把任何日志行（raw 或 decoded）写入数据库**。事件库只存事件元数据 + 截断到 4 KB 的 `raw_line`，不存储日志正文流。

【MUST】解码输出的 `.decoded.log` 必须是**人类可读的纯文本**：每行一条记录，UTF-8 编码，去除控制字符，便于运维直接 `tail` / `grep` 查看。

---

## 2. 核心约束与设计决策

| 约束 | 决策 |
|------|------|
| 多控制器、多时钟域 | 以 **tbox** 时间为统一基准；其它源通过 offset 映射；**不写回**任何源文件。 |
| MCU/kernel 重启后存在 1970/2000 伪时间戳 | 预扫描以 `MIN_VALID_TS = 2020-01-01` 截断；伪值段以"未同步段"标注（保留行号区间，**不丢弃**日志行）。 |
| 同一类日志可能多文件、甚至同名 | 落盘文件名：`{file_id}__{original_name}`，**绝不覆盖**；catalog 索引以 `file_id` 为主键。 |
| 性能敏感 | 流式 + 进程池/线程池流水线；解析结果仅写索引与事件，不写日志行。 |
| 查询窗口跨度从 1 小时到 1 周 | 5 分钟桶索引 + 字节偏移；catalog 全局元数据预筛文件。 |
| 重要事件无人工字典 | 规则即配置（YAML），加载时合并编译为单一正则，单次扫描多规则匹配。 |
| 控制器种类未来会增加 | Decoder/Classifier/EventRules 全部插件化，新增控制器无需改核心代码。 |

---

## 3. 总体架构

```
                     ┌────────────────────────────────────────────┐
   上传压缩包  ───▶  │  Ingest Pipeline（一次性管线，按 bundle）  │
                     │                                            │
                     │  Stage 1  Extract     ── 流式解压          │
                     │  Stage 2  Classify    ── 控制器归类        │
                     │  Stage 3  Store(raw)  ── 落盘（防覆盖）    │
                     │  Stage 4  Decode      ── DLT/文本解码      │
                     │  Stage 5  Prescan     ── 单遍提取：        │
                     │                          · 重要事件        │
                     │                          · 锚点候选        │
                     │                          · 时间范围        │
                     │                          · 5min 桶索引     │
                     │  Stage 6  Align       ── 以 tbox 为基准    │
                     │                          · 直接对齐        │
                     │                          · 两跳对齐        │
                     │                          · 未同步段标注    │
                     │  Stage 7  Persist     ── 写 catalog/事件   │
                     └─────────────────────┬──────────────────────┘
                                           │
                                           ▼
                ┌──────────────────────────────────────────────┐
                │  Query Service（在线服务，按 bundle）        │
                │   GET /logs?start&end&controllers&format     │
                │   GET /events?types&start&end                │
                │   · 全量版 / 精简版                          │
                │   · 流式 NDJSON                              │
                └──────────────────────────────────────────────┘
```

阶段间通过队列连接，Stage 4–5 可并发处理多文件；Stage 6 为 bundle 级聚合，必须等 Stage 5 全部完成。

---

## 4. 项目目录结构（建议）

```
log_pipeline/
├── config/
│   ├── classifier_rules.yaml
│   ├── event_rules.yaml
│   ├── anchor_rules.yaml
│   ├── slim_rules.yaml
│   └── controllers.yaml
├── log_pipeline/
│   ├── __init__.py
│   ├── interfaces.py              # 所有 Protocol/ABC
│   ├── ingest/
│   │   ├── uploader.py
│   │   ├── extractor.py
│   │   └── classifier.py
│   ├── decoders/
│   │   ├── base.py
│   │   ├── dlt.py
│   │   ├── android_logcat.py
│   │   ├── tbox_text.py
│   │   ├── kernel_dmesg.py
│   │   └── mcu_text.py
│   ├── prescan/
│   │   ├── prescanner.py
│   │   └── rule_engine.py
│   ├── alignment/
│   │   ├── time_aligner.py
│   │   └── unsynced_segments.py
│   ├── index/
│   │   ├── file_index.py
│   │   └── catalog.py
│   ├── storage/
│   │   ├── filestore.py
│   │   └── eventdb.py
│   ├── query/
│   │   ├── range_query.py
│   │   └── slim_filter.py
│   └── api/
│       └── http.py
└── tests/
    ├── fixtures/
    │   └── bundles/
    └── ...
```

---

## 5. 数据模型

【MUST】所有数据模型使用 `@dataclass(frozen=True)` 或 `pydantic.BaseModel`，禁止裸 `dict` 跨模块传递。

```python
from enum import Enum
from dataclasses import dataclass
from typing import Literal, Optional
from uuid import UUID

class ControllerType(str, Enum):
    ANDROID = "android"
    TBOX    = "tbox"
    FOTA    = "fota"
    MCU     = "mcu"
    KERNEL  = "kernel"
    UNKNOWN = "unknown"        # 分类失败时回落，不丢弃文件

class AlignmentStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED  = "failed"

class AlignmentMethod(str, Enum):
    DIRECT  = "direct"
    TWO_HOP = "two_hop"
    NONE    = "none"

@dataclass(frozen=True)
class LogFileMeta:
    file_id: UUID
    bundle_id: UUID
    controller: ControllerType
    original_name: str
    stored_path: str
    decoded_path: Optional[str]
    raw_ts_min: Optional[float]
    raw_ts_max: Optional[float]
    valid_ts_min: Optional[float]
    valid_ts_max: Optional[float]
    unsynced_line_ranges: list[tuple[int, int]]
    line_count: int
    bucket_index_path: str
    clock_offset: Optional[float]
    offset_confidence: float
    offset_method: AlignmentMethod

@dataclass(frozen=True)
class AnchorCandidate:
    anchor_type: str
    controller: ControllerType
    raw_timestamp: float
    line_no: int
    confidence: float
    fields: dict

@dataclass(frozen=True)
class ImportantEvent:
    event_id: UUID
    bundle_id: UUID
    file_id: UUID
    controller: ControllerType
    event_type: str
    raw_timestamp: float
    aligned_timestamp: Optional[float]   # None 表示该事件位于未同步段
    alignment_quality: float
    line_no: int
    raw_line: str                        # 截断到 4 KB
    extracted_fields: dict

@dataclass(frozen=True)
class BundleAlignmentSummary:
    status: AlignmentStatus
    base_clock: ControllerType           # 通常为 tbox，降级时可能为 android
    sources: dict[ControllerType, "SourceOffset"]

@dataclass(frozen=True)
class SourceOffset:
    offset: Optional[float]              # source_to_base，秒
    confidence: float                    # 0~1
    method: AlignmentMethod
    sample_count: int
```

---

## 6. 关键算法

### 6.1 解压与防覆盖落盘

【MUST】解压时遇到同名文件**绝不覆盖**。统一落盘策略：

```
{store_root}/{bundle_id}/{controller}/{file_id}__{original_name}
```

- `file_id` = `uuid4()`
- 若分类失败，落盘到 `controller=unknown` 子目录，**仍保留**。
- 解压过程流式：使用 `zipfile.open()` / `tarfile.extractfile()` 返回的文件对象，避免一次性 `extractall`。
- 大文件（> 1 GB）须支持断点续传校验：写入临时名 `.partial` → 校验大小 → 原子重命名。

### 6.2 控制器分类

【MUST】按以下优先级判定（短路）：

1. 路径优先：解压后路径中的目录名（如 `tbox/`, `android/log/`），匹配 `controllers.yaml` 中的 `path_patterns`。
2. 文件名：扩展名（`.dlt` → 候选集合）+ 文件名前缀（如 `dmesg*` → kernel）。
3. 内容嗅探：读取首 N KB（默认 8 KB），匹配特征：
   - DLT 魔术字 `b"DLT\x01"`
   - Android logcat 行首正则 `^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+\d+\s+\d+\s+[VDIWEF]\s+`
   - tbox 文本日志特征
   - kernel dmesg 特征 `^\[\s*\d+\.\d+\]`

4. 仍无法判定 → `ControllerType.UNKNOWN`。

`config/classifier_rules.yaml` 示例：
```yaml
controllers:
  - type: tbox
    path_patterns: ["**/tbox/**", "**/TBOX/**"]
    name_patterns: ["tbox_*.log", "tbox*.txt"]
    content_signatures:
      - regex: "^\\[TBOX\\]"
  - type: android
    path_patterns: ["**/android/**", "**/sys_log/**"]
    name_patterns: ["logcat*", "main*.log", "*.dlt"]
    content_signatures:
      - magic_bytes: "DLT\x01"
      - regex: "^\\d{2}-\\d{2}\\s+\\d{2}:\\d{2}:\\d{2}"
  # ...
```

### 6.3 解码器（Decoder）抽象

【MUST】所有解码器实现统一 Protocol：

```python
class LogDecoder(Protocol):
    controller: ControllerType

    def can_decode(self, file_path: str) -> bool: ...

    def iter_lines(self, file_path: str) -> Iterator[DecodedLine]:
        """流式产出解码后的行，必须是 generator"""
        ...

    def decoded_format(self) -> Literal["text", "ndjson"]: ...
```

```python
@dataclass(frozen=True)
class DecodedLine:
    line_no: int
    byte_offset: int
    raw_timestamp: Optional[float]   # 解析失败为 None
    text: str                        # 去除行尾换行
```

【MUST】DLT 解码：
- 使用流式 message 解析（不要 `read_all`）。
- 每条 message 输出一行：`<ts> <ECU> <APID> <CTID> <payload>`。
- 解码后落盘到 `{stored_path}.decoded.log`，路径填入 `LogFileMeta.decoded_path`。
- 保留原始 DLT 文件以便重处理。

【MUST】文本类解码器（android/tbox/kernel/mcu）：
- 时间戳解析采用每控制器独立的正则与时区策略。
- 跨年（如 dmesg 相对时间）需结合文件 mtime 或后续 anchor 修正——本阶段先输出**相对时间**，对齐阶段统一处理。

### 6.4 预扫描（Prescanner）

【MUST】对每个解码后的文件**单遍**完成下列任务：

```
for each DecodedLine:
    # 时间范围与桶索引
    if line.raw_timestamp is not None and line.raw_timestamp >= MIN_VALID_TS:
        update_valid_range(line.raw_timestamp)
        bucket_index.append(bucket(line.raw_timestamp), line.byte_offset, line.line_no)
    else:
        unsynced_buffer.add(line.line_no)

    update_raw_range(line.raw_timestamp)

    # 事件 + 锚点（合并正则一次匹配）
    for match in compiled_rules[controller].finditer(line.text):
        if match.is_event:    yield ImportantEvent(...)
        if match.is_anchor:   collect AnchorCandidate(...)
```

要点：
- `MIN_VALID_TS = 1577836800.0` (`2020-01-01 00:00:00 UTC`)，常量定义在 `prescan/prescanner.py` 顶部。
- 未同步段以**连续行号区间**记录，最终合并为 `[(start, end), ...]`。
- 5 分钟桶：`bucket_id = floor(raw_ts / 300)`；每桶记录 `(byte_offset_start, line_no_start)`。
- 多文件并发：进程池（推荐 `concurrent.futures.ProcessPoolExecutor`，worker 数 = CPU 数）。

【SHOULD】事件规则与锚点规则在加载时**合并**为单一 `re.Pattern`，使用命名组区分规则名：
```python
combined = re.compile(
    "|".join(f"(?P<{rule.id}>{rule.pattern})" for rule in rules)
)
```

### 6.5 时间对齐（以 tbox 为基准）

#### 6.5.1 锚点定义

【MUST】`config/anchor_rules.yaml` 维护以下锚点类型（最少集合）：

| 锚点类型 | 关键词 | 参与源 | 置信度 | 备注 |
|---------|--------|--------|--------|------|
| `system_boot` | boot, startup, init, starting | android, mcu, kernel, tbox | 0.90 | |
| `network_connected` | network connected, wifi connected | android, fota, tbox | 0.85 | |
| `fota_download_start` | download start, downloading | android, fota, mcu, tbox | 0.95 | |
| `fota_install_start` | install start, flashing | android, fota, mcu, tbox | 0.95 | |
| `system_reboot` | reboot, restart, rebooting | android, mcu, kernel, tbox | 0.90 | |
| `tbox_clock_sync` | rtc set hw, time sync, gps time, ntp sync | tbox, mcu | 0.98 | tbox→MCU 校时广播 |

【MUST】`tbox_clock_sync` 锚点用途：
- 在 mcu/kernel 中识别"伪时间→真实时间"的**跳变点**，作为未同步段的**结束位置**。
- 为两跳对齐提供 `tbox ↔ mcu` 直接锚点，避免必须借道 android。

#### 6.5.2 直接对齐

【MUST】对每个非 tbox 源 S，从锚点候选中筛出"同时含 tbox 与 S 时间戳"的锚点对（按 `anchor_type` + 时间邻近性配对）：

```
配对判据：同 anchor_type，且 |tbox_ts - S_ts_corrected| < window_seconds
window_seconds 初值 60；锚点稀疏（< 3 对）时放宽至 600。
```

```
offset_S_to_tbox = weighted_mean(
    samples = [tbox_ts(a) - S_ts(a)  for a in matched_pairs],
    weights = [a.confidence          for a in matched_pairs]
)

confidence = min(n/2, 1.0) × avg_anchor_confidence × consistency_factor
  其中 consistency_factor: 当 stdev > 5s 时线性衰减至 0.6
```

#### 6.5.3 两跳对齐

【MUST】触发条件：
1. tbox 已完成对齐（`offsets[tbox].confidence ≥ 0.6`，但实际 tbox 自身 offset = 0）。
2. 目标源 S 的直接对齐缺失，或 `confidence < 0.7`。
3. 存在桥接源 B（通常为 android）满足：B 与 tbox、B 与 S 都有锚点。

公式：
```
offset_S_to_tbox = offset_B_to_tbox + (B_ts(a) - S_ts(a))   for each anchor a
```

【MUST】两跳结果置信度：
```
two_hop_conf = anchor.confidence × offset_B.confidence × 0.95
```
其中 `0.95` 为链式误差惩罚因子。两跳结果只在 `two_hop_conf > direct_conf` 时替换直接结果。

#### 6.5.4 未同步段处理

【MUST】对 mcu / kernel：
- 若文件中存在 `tbox_clock_sync` 接收点（line_no = K）：
  - `unsynced_line_ranges = [(0, K-1)]`
  - 仅 K 之后的行参与 offset 计算
- 若不存在 `tbox_clock_sync` 接收点：
  - 若所有时间戳 `< MIN_VALID_TS`：整个文件标记为未同步，`offset = None`
  - 否则按时间戳是否 `>= MIN_VALID_TS` 划分行号区间

【MUST】未同步段内的日志行**不丢弃**，查询时通过 `include_unsynced=true` 仍可访问，`aligned_timestamp = None`。

#### 6.5.5 状态评估

| 状态 | 条件 |
|------|------|
| `SUCCESS` | tbox 为基准且全部目标源 `confidence ≥ 0.8` |
| `PARTIAL` | tbox 有效，且至少 50% 目标源对齐成功；其余源 `offset = None` |
| `FAILED`  | tbox 锚点不足无法作为基准；触发降级（见 §8） |

#### 6.5.6 偏移合理性校验

【MUST】计算出的 offset 若 `abs(offset) > 30 × 86400`（30 天），视为异常：
- 该源 `offset = None`，`method = NONE`，`confidence = 0`。
- 在 alignment_summary 中输出 warning。

### 6.6 索引：5 分钟桶 + 字节偏移

【MUST】每个文件生成桶索引文件 `{file_id}.idx`（建议二进制 / parquet）：

```
records = [
  (bucket_id: int64, byte_offset_start: int64, line_no_start: int64),
  ...
]
按 bucket_id 升序、连续；查询时二分定位。
```

桶大小：5 分钟（300 秒）。1 周区间最多 2016 桶，单文件索引可全内存加载。

【MUST】Catalog 全局表：

```sql
CREATE TABLE catalog (
  file_id          UUID PRIMARY KEY,
  bundle_id        UUID NOT NULL,
  controller       TEXT NOT NULL,
  original_name    TEXT NOT NULL,
  stored_path      TEXT NOT NULL,
  decoded_path     TEXT,
  valid_ts_min     DOUBLE PRECISION,
  valid_ts_max     DOUBLE PRECISION,
  raw_ts_min       DOUBLE PRECISION,
  raw_ts_max       DOUBLE PRECISION,
  clock_offset     DOUBLE PRECISION,
  offset_confidence REAL,
  offset_method    TEXT,
  line_count       BIGINT,
  bucket_index_path TEXT,
  unsynced_ranges_json TEXT,
  created_at       TIMESTAMPTZ
);
CREATE INDEX idx_catalog_bundle_ctrl ON catalog(bundle_id, controller);
CREATE INDEX idx_catalog_time ON catalog(bundle_id, valid_ts_min, valid_ts_max);
```

### 6.7 重要事件规则（外置）

【MUST】`config/event_rules.yaml`，初始最小集合（实际部署可扩展）：

```yaml
events:
  - type: system_reboot
    applies_to: [android, mcu, kernel, tbox]
    patterns:
      - regex: "(?i)\\b(reboot|restart|rebooting)\\b"
    fields:
      reason: { regex: "reason=([\\w-]+)" }

  - type: system_boot
    applies_to: [android, mcu, kernel, tbox]
    patterns:
      - regex: "(?i)\\b(boot completed|system started|init done)\\b"

  - type: fota_notify
    applies_to: [android, fota, tbox]
    patterns:
      - keyword_all: ["FOTA", "notify"]
      - regex: "(?i)ota.*available"

  - type: fota_download_start
    applies_to: [android, fota, tbox]
    patterns:
      - keyword_all: ["FOTA", "download", "start"]

  - type: fota_install_start
    applies_to: [android, fota, mcu, tbox]
    patterns:
      - keyword_any: ["install start", "flashing", "begin install"]

  - type: gear_shift
    applies_to: [mcu]
    patterns:
      - regex: "GEAR\\s*->\\s*(?P<gear>[PRND])\\b"
    fields:
      gear: { from_group: gear }

  - type: door_open
    applies_to: [mcu]
    patterns:
      - regex: "DOOR_(?P<door>FL|FR|RL|RR|TRUNK)_OPEN"
    fields:
      door: { from_group: door }

  - type: door_close
    applies_to: [mcu]
    patterns:
      - regex: "DOOR_(?P<door>FL|FR|RL|RR|TRUNK)_CLOSE"

  - type: charging_start
    applies_to: [mcu, tbox]
    patterns:
      - keyword_any: ["charging started", "CHG_START", "charge_begin"]

  - type: charging_end
    applies_to: [mcu, tbox]
    patterns:
      - keyword_any: ["charging stopped", "CHG_END", "charge_complete"]

  - type: brake_event
    applies_to: [mcu]
    patterns:
      - regex: "(?i)brake.*pressed|EBS\\s+active"

  - type: vehicle_unlock
    applies_to: [tbox, mcu]
    patterns:
      - keyword_any: ["unlock", "UNLOCK_OK"]

  - type: vehicle_lock
    applies_to: [tbox, mcu]
    patterns:
      - keyword_any: ["lock_ok", "LOCK_OK", "vehicle locked"]
```

字段提取支持：
- `regex` + 命名捕获组 → 自动转为 `extracted_fields`
- `keyword_all`：所有词（不区分大小写）必须命中
- `keyword_any`：任一词命中

### 6.8 精简版（slim）输出

【MUST】`config/slim_rules.yaml`：

```yaml
slim:
  drop:
    - controller: android
      patterns:
        - "(?i)I/ActivityManager.*Displayed"
        - "^\\s*V/"                     # verbose
        - "I/chatty.*identical.*lines"
    - controller: kernel
      patterns:
        - "audit:"
        - "wlan: rate"
    - controller: tbox
      patterns:
        - "(?i)heartbeat"
        - "(?i)keepalive"

  keep_always:                          # 任何控制器、任何情况都保留
    - "(?i)\\bpanic\\b"
    - "(?i)\\bfatal\\b"
    - "(?i)\\bexception\\b"
    - "(?i)\\bBUG:\\s"
    - "(?i)\\boom-killer\\b"
```

【MUST】Slim 过滤动态生成（不预先落盘 slim 文件），实现为流式 `keep_always > drop > pass-through` 三级判定。

---

## 7. 接口契约

【MUST】所有时间使用 ISO8601 字符串或 Unix 秒（float），返回值统一 UTC。

### 7.1 上传

```
POST /api/bundles
Content-Type: multipart/form-data
Body: file=<archive>

→ 200
{
  "bundle_id": "uuid",
  "status": "queued"
}
```

### 7.2 处理状态

```
GET /api/bundles/{bundle_id}

→ 200
{
  "bundle_id": "...",
  "status": "queued | extracting | decoding | prescanning | aligning | done | failed",
  "progress": 0.72,
  "files": [<LogFileMeta>...],
  "alignment_summary": {
    "status": "success | partial | failed",
    "base_clock": "tbox",
    "sources": {
      "android": {"offset": 0.32, "confidence": 0.94, "method": "direct", "sample_count": 6},
      "mcu":     {"offset": -1.2, "confidence": 0.78, "method": "two_hop", "sample_count": 4},
      "kernel":  {"offset": null, "confidence": 0.0, "method": "none", "sample_count": 0}
    },
    "warnings": [
      "kernel: no clock_sync anchor found; entire file marked unsynced"
    ]
  }
}
```

### 7.3 时间段日志查询

```
GET /api/bundles/{bundle_id}/logs
Query:
  start=2025-04-01T08:00:00Z          # 必填，统一时钟（tbox）
  end=2025-04-01T09:00:00Z            # 必填
  controllers=android,mcu,tbox        # 可选，缺省全部
  format=full|slim                    # 缺省 full
  include_unsynced=false              # 缺省 false
  limit=100000                        # 缺省 1_000_000，硬上限 5_000_000

→ 200 application/x-ndjson  (流式)
{"controller":"tbox","file_id":"...","aligned_ts":1712044800.123,"raw_ts":1712044800.123,"line_no":12345,"line":"..."}
{"controller":"mcu","file_id":"...","aligned_ts":1712044801.443,"raw_ts":1712044802.643,"line_no":98,"line":"GEAR -> D"}
...
```

【MUST】响应头：
- `X-Total-Files-Scanned`
- `X-Truncated: true|false`（命中 limit）

### 7.4 重要事件查询

```
GET /api/bundles/{bundle_id}/events
Query:
  types=fota_download_start,system_reboot   # 可选
  controllers=mcu,tbox                      # 可选
  start=...&end=...                         # 可选

→ 200 application/json
[<ImportantEvent>...]
```

### 7.5 错误返回

【MUST】错误统一格式：
```json
{ "error": { "code": "BUNDLE_NOT_FOUND", "message": "..." } }
```
HTTP 状态码：4xx 客户端错误、5xx 服务端错误。

---

## 8. 降级策略

【MUST】按以下顺序尝试：

1. **tbox 锚点不足以校准其它源** → 仅返回 tbox 自身已对齐的范围；其它源 `offset=None`，状态 `PARTIAL`。
2. **tbox 完全无锚点或文件缺失** → 临时以 android 为基准（`base_clock=android`），并在 alignment_summary 标注 `degraded=true`。
3. **离线对齐 FAILED 但 catalog 中已有有效偏移**（重处理场景）：升级为 `PARTIAL`。
4. **某源完全无锚点** → 保留为 `offset=None`；查询时该源行 `aligned_ts=null` 并附 `clock_unaligned=true`。

【MUST】所有降级路径都需写 `BundleProcessingLog`（见 §10），便于审计。

---

## 9. 性能要求

| 项 | 目标 |
|----|------|
| 单包（解压后 ≤ 2 GB） | ≤ 3 分钟（8C / 16 GB / SSD） |
| DLT 解码 | ≥ 50 MB/s/进程 |
| 1 小时区间查询响应 | < 2 秒（端到端） |
| 1 周区间查询首字节 | < 5 秒（流式） |
| 事件库写入 | 批量 `executemany`，单事务，单包 ≤ 5 秒 |

【MUST】实现要点：
- 解压 / 解码 / 预扫描三阶段流水线化（`asyncio.Queue` 或 `multiprocessing.Queue`）。
- CPU 密集（DLT、正则）走 `ProcessPoolExecutor`；IO（落盘、DB）走线程池。
- 锚点与事件规则在 worker 进程启动时**一次性编译**并缓存。
- 日志行**绝不全量入库**。
- 索引文件采用二进制紧凑格式（建议每记录 24 字节定长）。

---

## 10. 可观测性

【MUST】每个 bundle 生成一份处理日志：
```
{store_root}/{bundle_id}/_processing.log
```
内容包括：
- 阶段开始 / 结束时间戳
- 文件数 / 各控制器分类计数
- 解码失败文件清单
- 锚点统计（每类型、每源）
- 对齐结果与降级原因
- 事件数（按类型）

【SHOULD】Prometheus 指标：
- `pipeline_stage_duration_seconds{stage}`
- `pipeline_files_total{controller, status}`
- `pipeline_events_extracted_total{event_type}`
- `alignment_offset_seconds{controller}`（gauge，最新值）
- `alignment_confidence{controller}`（gauge）

---

## 11. 测试策略

### 11.1 单元测试

【MUST】覆盖：
- 每个 Decoder：给定 fixture，断言行数、首/末时间戳、字段。
- Classifier：跨控制器混淆样本、UNKNOWN 回落。
- 锚点匹配：合成日志，断言锚点数量与 offset。
- 两跳对齐：构造仅有 android↔mcu 锚点的场景，验证两跳。
- 未同步段标注：构造从 1970 跳到 2025 的 mcu 日志，验证 line_range 正确。
- 30 天阈值：注入异常 offset，验证被剔除。
- 防覆盖：注入两份同名文件，验证 catalog 含两条记录、两文件均存在。

### 11.2 集成测试

【MUST】端到端 fixture 包：
- `bundle_minimal.zip`：每控制器 1 文件，规模小。
- `bundle_reboot.zip`：MCU 含重启 + 校时跳变。
- `bundle_no_tbox.zip`：缺 tbox，验证降级。
- `bundle_dup_names.zip`：多控制器存在同名 `main.log`。
- `bundle_large.tar.gz`：≥ 1 GB，性能基准。

每个 fixture 配套 `expected.json`，列出预期文件数、事件数、alignment_summary。

### 11.3 性能基准

【SHOULD】`pytest-benchmark` 或 `pyperf`：
- DLT 解码吞吐
- 预扫描吞吐
- 1 小时 / 1 周查询延迟

CI 上跑性能回归（允许 ±20% 波动）。

### 11.4 回归数据集

【MUST】`tests/fixtures/bundles/` 维护至少 5 份**脱敏**真实样本，CI 全量跑通。

---

## 12. 里程碑（推荐实现顺序）

| # | 里程碑 | 交付物 | 退出标准 |
|---|--------|--------|----------|
| M1 | Skeleton & Storage | uploader / extractor / classifier / filestore / catalog 表 | 上传压缩包 → 文件分类落盘 → catalog 中能查到 |
| M2 | Decoders | DLT + 4 个文本解码器，统一接口 | 每 Decoder 单测通过；解码后落盘 |
| M3 | Prescan & Events | prescanner + rule_engine + event_rules.yaml + eventdb | 给定 fixture，事件入库数与预期一致 |
| M4 | Alignment | time_aligner + unsynced_segments + 两跳 | 三种对齐 fixture 全通过 |
| M5 | Query | range_query + slim_filter + HTTP API | 1 小时 / 1 周区间查询正确且符合性能目标 |
| M6 | Hardening | 降级路径、监控指标、性能调优、回归 | CI 全绿，性能基准达标 |

每个 M 独立可交付、独立可测；M1–M3 可并行（接口先行）。

---

## 13. 给 Claude Code 的实现指引

【MUST】**契约先行**：每个模块先在 `interfaces.py` 写 Protocol/ABC，再写实现。
【MUST】**配置外置**：事件规则、锚点规则、分类规则、精简规则全部 YAML，禁止硬编码到 `.py`。
【MUST】**不写回时间戳**：所有 `aligned_ts` 在查询时即时计算（`raw_ts + offset`）。
【MUST】**全量保留原始文件**：包括 unsynced 全段、同名文件、分类失败文件。
【MUST】**流式 everything**：解压 / 解码 / 扫描 / 查询全部 generator/iterator，禁止 `read_all` 大文件。
【MUST】**对齐可重算**：所有锚点候选保存到 catalog（或 sidecar 文件），便于规则更新后只重跑 alignment。
【MUST】**日志即审计**：处理过程关键决策（如"以 android 为临时基准"）写入 `_processing.log`。
【MUST】**错误不静默**：解码失败、分类失败、对齐失败必须在 alignment_summary 与 _processing.log 中显式记录。
【SHOULD】所有公共接口加类型标注（`from __future__ import annotations`）。
【SHOULD】使用 `pydantic` 做配置文件 schema 校验，启动失败优于运行时崩溃。
【MAY】使用 `polars` 加速桶索引构建与查询。

---

## 14. 术语表

| 术语 | 含义 |
|------|------|
| bundle | 一次上传的整车日志压缩包 |
| controller | 控制器，对应一类日志（android/tbox/mcu/kernel/fota/...） |
| anchor | 锚点事件，跨源出现的相同事件，用于计算时钟偏移 |
| offset | 源时钟到 tbox 时钟的差值（秒），`tbox_ts = src_ts + offset` |
| unsynced segment | 未同步段，源时钟尚未与 tbox 校时之前的日志行区间 |
| bucket | 索引桶，5 分钟时间窗口 |
| slim | 精简版输出，去除对故障判断无增量的行 |
| two-hop | 两跳对齐，借助桥接源（通常 android）间接计算 offset |

---

## 15. 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-04-28 | 1.0 | 初版，对齐目标与实现契约 |
| 2026-04-28 | 1.1 | 新增 §1.4 存储策略总览（强约束）：分类/解码后日志落盘可读文本不入库；重要事件入库；精简版动态过滤不存储 |
| 2026-04-29 | 1.2 | M1–M3 实现落地：`log_pipeline/` 包成型；契约不变；数据模型 `LogFileMeta` 在保留 `original_name`（basename）基础上新增 `bundle_relative_path` 字段（嵌套 zip 与同名文件溯源）；锚点采用 SQLite `anchors` 表持久化（§13 SHOULD 二选一中的 catalog 路径） |
| 2026-04-29 | 1.3 | M4–M5 实现落地：alignment 直接+两跳+30 天合理性+android 降级；`bundles.alignment_summary_json` 写入；`/logs` 流式 NDJSON 末尾追加 `_meta` 行（authoritative truncation 信号，X-Truncated header 仅为预估提示）；`/events` 支持 types/controllers/start/end 过滤；slim 三级判定（keep_always > drop > pass）查询时动态过滤不入库 |
| 2026-04-29 | 1.4 | M6 hardening：PrescanStage `ProcessPoolExecutor` 并行（fork ctx，按文件分发，主进程串行 DB 写）→ 1614s → 204s（7.9x）；`/logs` 用桶索引 `_byte_window_for_range` 计算 start+end 两端字节，1h 窗 12.45s → 0.07s（达 §9 < 2s 目标）；新增 `/metrics` Prometheus 文本端点（bundles_total/files_total/events_extracted_total/alignment_offset_seconds/alignment_confidence） |
```