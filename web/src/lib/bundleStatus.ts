export type BundleStatusPayload = {
  bundle_id?: string;
  status?: string;
  progress?: number;
  archive_filename?: string;
  archive_size_bytes?: number;
  error?: string | null;
  file_count?: number;
  files_by_controller?: Record<string, number>;
};

const BUNDLE_STAGE_LABELS: Record<string, string> = {
  queued: "已入队，等待处理",
  extracting: "步骤 1/4：解压与分类中",
  decoding: "步骤 2/4：日志解码中",
  prescanning: "步骤 3/4：预扫描与事件抽取中",
  aligning: "步骤 4/4：时间对齐中",
  done: "处理完成",
  failed: "处理失败",
};

export const getBundleStageLabel = (status: string | null | undefined): string => {
  const normalized = typeof status === "string" ? status.trim() : "";
  if (!normalized) return "处理中";
  return BUNDLE_STAGE_LABELS[normalized] ?? `处理中（${normalized}）`;
};

export const getBundleQueryErrorText = (
  payload: unknown,
  fallbackStatus: number
): string => {
  if (!payload || typeof payload !== "object") {
    return `查询失败: ${fallbackStatus}`;
  }
  const candidate = payload as {
    detail?: string;
    error?: string | { message?: string } | null;
  };
  const nestedError =
    typeof candidate.error === "object" && candidate.error
      ? candidate.error.message
      : undefined;
  const directError = typeof candidate.error === "string" ? candidate.error : undefined;
  const detail = candidate.detail;
  return `查询失败: ${detail || nestedError || directError || fallbackStatus}`;
};

export const formatBundleStatusDetails = (payload: BundleStatusPayload): string => {
  const lines: string[] = [];
  const stageLabel = getBundleStageLabel(payload.status);
  lines.push(`状态: ${stageLabel}`);
  if (payload.status && payload.status !== "done" && payload.status !== "failed") {
    lines.push(`阶段标识: ${payload.status}`);
  }
  if (typeof payload.progress === "number") {
    lines.push(`进度: ${Math.round(payload.progress * 100)}%`);
  }
  if (typeof payload.file_count === "number") {
    lines.push(`已分类文件: ${payload.file_count}`);
  }
  if (payload.files_by_controller && Object.keys(payload.files_by_controller).length > 0) {
    const parts = Object.entries(payload.files_by_controller)
      .map(([controller, count]) => `${controller}=${count}`)
      .join(", ");
    lines.push(`按控制器: ${parts}`);
  }
  if (payload.error) {
    lines.push(`错误: ${payload.error}`);
  }
  return lines.join("\n");
};
