import { AgentStep, SourceReference } from "./types";

export interface MockResponse {
  scenarioId: string;
  query: string;
  steps: AgentStep[];
  content: string;
  sources: SourceReference[];
  confidenceLevel: string;
}

const FOTA_DIAGNOSTIC_RESPONSE: MockResponse = {
  scenarioId: "fota-diagnostic",
  query: "iCGM为何挂死",
  steps: [
    {
      stepNumber: 1,
      agentName: "Parallel Orchestrator",
      status: "completed",
      statusText: "Parallely Orchestrating...",
      result: "已调度 Log Analytics Agent 进行并行分析",
    },
    {
      stepNumber: 2,
      agentName: "Log Analytics Agent",
      status: "completed",
      statusText: "Reading the logs and analyzing...",
      result: `核心异常分析：

1. **MPU 升级包下载校验失败**
   - 时间戳: 08:57:58 - 日志记录 HttpDownloadManager 开始下载 2.077 GB MPU升级包
   - 时间戳: 09:01:55 - 下载完成 (download finish)，但校验阶段报错
   - 关键错误: \`verifyPackage: /data/fota/mpu_update.zip not exist\`
   - 实际写入大小: \`write file size = 0(0 B)\`

2. **iCGM 模块进入死循环**
   - 时间戳: 09:02:09 - iCGM 检测到升级包校验失败
   - 触发 \`[FotaFlashImpl]-usbReboot\` 重启流程
   - 重启后再次尝试下载，形成"下载 -> 校验失败 -> 重启 -> 再下载"的死循环

3. **MCU/IPK 状态不一致**
   - MCU 已完成刷写进入等待状态
   - IPK 仍在等待 iCGM 完成升级协调
   - 状态机卡在 FLASHING_IN_PROGRESS

4. **USB 通信异常**
   - \`[FotaFlashImpl]-usbReboot\` 多次调用未能恢复正常状态
   - USB 设备枚举超时（timeout=30000ms）`,
    },
    {
      stepNumber: 3,
      agentName: "Agent Interface",
      status: "completed",
      statusText: "Generating the Final Response...",
    },
  ],
  content: `## 信息分析

**主要来源：** 车辆系统日志（2025-09-11 实际升级日志）
**置信度：** 高

---

## 技术解答

### 关键发现

iCGM 挂死的直接原因是 **MPU 升级包下载后校验失败**，导致 FOTA 状态机进入死循环。

### 具体过程

1. **08:57:58** — HttpDownloadManager 开始下载 2.077 GB MPU 升级包
2. **09:01:55** — 下载完成（\`download successful\`），但实际文件写入大小为 0 字节
3. **09:02:09** — 校验阶段报错：\`verifyPackage: /data/fota/mpu_update.zip not exist\`
4. **09:03:05** — iCGM 触发 \`[FotaFlashImpl]-usbReboot\`，尝试重启恢复
5. 重启后系统再次尝试下载，重复上述失败流程，形成**死循环**

### 根本原因分析

- 磁盘空间不足或文件系统写入异常，导致下载数据虽然传输完成但未持久化到磁盘
- FOTA 状态机缺少对"校验失败次数"的上限检查，缺乏有效的兜底机制
- \`usbReboot\` 作为恢复手段未能清除错误状态标记

---

## ⚠️ 安全提示

- iCGM 挂死期间，MCU 已完成刷写但处于等待状态，**车辆可能处于不完整的固件状态**
- 建议在下次 OTA 升级前，通过线下诊断工具确认所有 ECU 的固件版本一致性
- 勿在未恢复 iCGM 正常状态前进行下一次升级尝试

---

## 建议措施

1. **立即处理**：通过诊断工具强制重置 iCGM 的 FOTA 状态机，清除错误标记
2. **磁盘空间检查**：确认 \`/data/fota/\` 分区剩余空间是否充足（>3GB）
3. **流程优化**：建议在 FOTA 流程中增加校验失败重试上限（建议 ≤3 次）
4. **异常兜底**：校验失败达到上限后，自动回退到上一个稳定固件版本
5. **后续处理**：确认 MCU 和 IPK 的固件版本与预期一致，必要时手动触发同步刷写`,
  sources: [
    {
      title: "实际升级日志（2025-09-11）",
      type: "log",
    },
    {
      title: "FOTA状态机流程及异常场景处理技术要点2023Q3.pdf",
      url: "#",
      type: "pdf",
    },
  ],
  confidenceLevel: "高",
};

const FOTA_JIRA_RESPONSE: MockResponse = {
  scenarioId: "fota-jira",
  query: "iCGM为何挂死",
  steps: [
    {
      stepNumber: 1,
      agentName: "Parallel Orchestrator",
      status: "completed",
      statusText: "Parallely Orchestrating...",
      result: "已调度 Log Analytics Agent 和 Maxus Jira Agent 进行并行分析",
    },
    {
      stepNumber: 2,
      agentName: "Log Analytics Agent",
      status: "completed",
      statusText: "Reading the logs and analyzing...",
      result: `核心异常分析：

1. **MPU 升级包下载校验失败** — 下载 2.077 GB 完成后文件写入为 0 字节
2. **iCGM 进入死循环** — "下载 -> 校验失败 -> usbReboot -> 再下载"
3. **MCU/IPK 状态不一致** — 状态机卡在 FLASHING_IN_PROGRESS
4. **USB 通信异常** — usbReboot 多次调用未恢复`,
    },
    {
      stepNumber: 3,
      agentName: "Maxus Jira Agent",
      status: "completed",
      statusText: "Retrieved existing relevant Jira tickets and documents...",
      result: `检索到相关 Jira 工单和离线文档：

**类似历史 Jira 工单：**
- **FOTA-8765**: iCGM 升级过程中挂死，根因为 eMMC 写入超时
- **FOTA-9123**: MPU 升级包校验失败导致循环重启

**相关离线文档：**
- 《FOTA状态机流程及异常场景处理技术要点2023Q3.pdf》
- 《集中式升级刷写流程异常链路复盘2023-09》`,
    },
    {
      stepNumber: 4,
      agentName: "Agent Interface",
      status: "completed",
      statusText: "Generating the Final Response...",
    },
  ],
  content: `## Information Analysis

**Primary Sources:**
- [实际升级日志（2025-09-11）](#)
- [FOTA-8765: iCGM 升级过程中挂死](#)
- [FOTA-9123: MPU 升级包校验失败导致循环重启](#)
- [FOTA状态机流程及异常场景处理技术要点2023Q3.pdf](#)

**Confidence Level:** 高

---

## Technical Response

### 关键结论

iCGM 挂死的直接原因是 MPU 升级包下载后**文件未正确写入磁盘**（写入大小为 0 字节），导致校验失败并触发无限重启循环。

### 日志校验细节

| 时间戳 | 事件 | 状态 |
|---------|------|------|
| 08:57:58 | HttpDownloadManager 开始下载 | 正常 |
| 09:01:55 | download finish (2.077 GB) | 正常 |
| 09:01:56 | write file size = 0 (0 B) | ❌ 异常 |
| 09:02:09 | verifyPackage: not exist | ❌ 异常 |
| 09:03:05 | [FotaFlashImpl]-usbReboot | 🔄 重试 |

### 历史案例与最佳实践

根据 **FOTA-8765** 和 **FOTA-9123** 的修复记录：

1. **FOTA-8765** 的根因是 eMMC 在高温环境下写入超时，修复方案为增加 eMMC 写入超时阈值并加入温度检测保护
2. **FOTA-9123** 确认了校验失败后缺乏重试上限的问题，已在 v2.3.1 版本修复

### 解决/修复方案（已知最佳实践）

1. **强制重置 FOTA 状态机** — 通过诊断工具发送 0x3E 服务清除错误标记
2. **检查 eMMC 健康状态** — 读取 SMART 信息确认无坏块
3. **升级 FOTA 固件至 v2.3.1+** — 包含校验失败重试上限和兜底回退机制
4. **增加磁盘空间预检** — 下载前确认可用空间 ≥ 升级包大小 × 1.5
5. **温度保护** — 环境温度 > 65°C 时暂停升级流程

---

## ⚠️ 安全提示

- 当前 MCU 和 IPK 可能处于不一致的固件状态，建议线下全量检查
- 恢复前不要再次触发 OTA 升级

---

## Recommendations

1. **流程优化**：在 FOTA 流程中加入下载完整性预校验（MD5/SHA256）
2. **异常兜底**：连续 3 次校验失败后自动回退至上一稳定版本
3. **后续处理**：确认所有 ECU 固件版本一致，建议手动刷写对齐
4. **监控增强**：增加 eMMC 写入成功率和 FOTA 失败率的远程监控指标

---

**引用来源：**
- [实际升级日志（2025-09-11）](#)
- [FOTA-8765: iCGM 升级过程中挂死](#)
- [FOTA-9123: MPU 升级包校验失败导致循环重启](#)
- [《FOTA状态机流程及异常场景处理技术要点2023Q3.pdf》](#)`,
  sources: [
    {
      title: "实际升级日志（2025-09-11）",
      type: "log",
    },
    {
      title: "FOTA-8765: iCGM 升级过程中挂死",
      url: "#",
      type: "jira",
    },
    {
      title: "FOTA-9123: MPU 升级包校验失败导致循环重启",
      url: "#",
      type: "jira",
    },
    {
      title: "FOTA状态机流程及异常场景处理技术要点2023Q3.pdf",
      url: "#",
      type: "pdf",
    },
    {
      title: "集中式升级刷写流程异常链路复盘2023-09",
      url: "#",
      type: "document",
    },
  ],
  confidenceLevel: "高",
};

const ECU_FOLLOWUP_RESPONSE: MockResponse = {
  scenarioId: "fota-jira",
  query: "为何有一个ECU没有刷写完成",
  steps: [
    {
      stepNumber: 1,
      agentName: "Parallel Orchestrator",
      status: "completed",
      statusText: "Parallely Orchestrating...",
      result: "已调度 Log Analytics Agent 和 Maxus Jira Agent 进行并行分析",
    },
    {
      stepNumber: 2,
      agentName: "Log Analytics Agent",
      status: "completed",
      statusText: "Reading the logs and analyzing...",
      result: `ECU 刷写状态分析：

- IVI ECU: ✅ 刷写完成
- MCU ECU: ✅ 刷写完成
- IPK ECU: ❌ 未完成 — 等待 iCGM 协调信号
- iCGM ECU: ❌ 卡在校验失败循环`,
    },
    {
      stepNumber: 3,
      agentName: "Maxus Jira Agent",
      status: "completed",
      statusText: "Retrieved existing relevant Jira tickets and documents...",
      result: `相关 Jira 工单：
- **FOTA-8765**: ECU 刷写顺序依赖导致级联失败
- **FOTA-9123**: 确认 iCGM 作为升级协调者的关键角色`,
    },
    {
      stepNumber: 4,
      agentName: "Agent Interface",
      status: "completed",
      statusText: "Generating the Final Response...",
    },
  ],
  content: `## Information Analysis

**Primary Sources:**
- [实际升级日志（2025-09-11）](#)
- [FOTA-8765: ECU 刷写顺序依赖导致级联失败](#)
- [《集中式升级刷写流程异常链路复盘2023-09》](#)

**Confidence Level:** 高

---

## Technical Response

### 关键结论

**IPK ECU 未完成刷写**，直接原因是 iCGM 作为升级协调者进入死循环后，未能向 IPK 发送"可以开始刷写"的协调信号。

### 刷写依赖关系

\`\`\`
升级流程: IVI → MCU → iCGM(协调) → IPK
                        ↑
                    卡在此处（死循环）
\`\`\`

### 详细分析

1. **IVI 和 MCU** 在 iCGM 出问题之前已完成刷写，处于正常状态
2. **iCGM** 负责协调整体升级流程，当自身 MPU 升级包校验失败后进入死循环
3. **IPK** 收到"准备升级"指令后进入等待模式，等待 iCGM 发送 \`FLASH_START\` 信号
4. iCGM 死循环导致 \`FLASH_START\` 信号永远不会发出
5. IPK 等待超时后状态变为 \`FLASH_TIMEOUT\`，但未触发回退机制

### 风险评估

- 当前状态下 IPK 固件版本为旧版本，与已刷写的 IVI/MCU 存在**版本不匹配**风险
- 可能导致仪表盘显示异常或部分功能不可用

---

## Recommendations

1. 恢复 iCGM 后，手动触发 IPK 单独刷写
2. 验证 IVI/MCU/IPK 版本兼容性矩阵
3. 建议后续升级流程增加 ECU 独立回退能力，降低对协调者的强依赖`,
  sources: [
    {
      title: "实际升级日志（2025-09-11）",
      type: "log",
    },
    {
      title: "FOTA-8765: ECU 刷写顺序依赖导致级联失败",
      url: "#",
      type: "jira",
    },
    {
      title: "集中式升级刷写流程异常链路复盘2023-09",
      url: "#",
      type: "document",
    },
  ],
  confidenceLevel: "高",
};

const GENERIC_RESPONSES: Record<string, MockResponse> = {
  "air-filters": {
    scenarioId: "fota-diagnostic",
    query: "How to install air filters",
    steps: [
      {
        stepNumber: 1,
        agentName: "Parallel Orchestrator",
        status: "completed",
        statusText: "Parallely Orchestrating...",
        result: "已调度文档检索 Agent",
      },
      {
        stepNumber: 2,
        agentName: "Document Agent",
        status: "completed",
        statusText: "Searching maintenance documents...",
        result: "找到相关维修手册文档",
      },
      {
        stepNumber: 3,
        agentName: "Agent Interface",
        status: "completed",
        statusText: "Generating the Final Response...",
      },
    ],
    content: `## 技术解答

### 空气滤芯更换步骤

1. **准备工作**：确保发动机已熄火并冷却，打开前机舱盖
2. **定位滤芯盒**：空气滤芯盒位于发动机右侧，黑色塑料盒体
3. **打开滤芯盒**：松开 4 个金属卡扣，向上提起盒盖
4. **取出旧滤芯**：小心取出旧滤芯，注意安装方向标记
5. **清洁滤芯盒**：用干净抹布擦拭盒内灰尘和杂物
6. **安装新滤芯**：按照箭头方向放入新滤芯，确保密封圈到位
7. **关闭盒盖**：扣紧 4 个金属卡扣，确保密封良好

### ⚠️ 注意事项

- 建议每 15,000 公里或 12 个月更换一次
- 恶劣环境（沙尘、工地）建议缩短至 8,000 公里
- 使用原厂或同等质量的替代滤芯`,
    sources: [
      {
        title: "Maxus 车主使用手册 - 定期保养章节",
        type: "document",
      },
    ],
    confidenceLevel: "高",
  },
};

export function getMockResponse(
  scenarioId: string,
  query: string
): MockResponse {
  const normalizedQuery = query.toLowerCase().trim();

  if (
    normalizedQuery.includes("icgm") ||
    normalizedQuery.includes("挂死")
  ) {
    if (scenarioId === "fota-jira") {
      return FOTA_JIRA_RESPONSE;
    }
    return FOTA_DIAGNOSTIC_RESPONSE;
  }

  if (
    normalizedQuery.includes("ecu") ||
    normalizedQuery.includes("刷写")
  ) {
    return ECU_FOLLOWUP_RESPONSE;
  }

  if (normalizedQuery.includes("air filter") || normalizedQuery.includes("滤芯")) {
    return GENERIC_RESPONSES["air-filters"];
  }

  if (scenarioId === "fota-jira") {
    return FOTA_JIRA_RESPONSE;
  }
  return FOTA_DIAGNOSTIC_RESPONSE;
}
