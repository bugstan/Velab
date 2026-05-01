import {
  formatBundleStatusDetails,
  getBundleQueryErrorText,
  getBundleStageLabel,
} from "@/lib/bundleStatus";

describe("bundleStatus helpers", () => {
  it("maps known statuses and handles unknown/empty values", () => {
    expect(getBundleStageLabel("queued")).toBe("已入队，等待处理");
    expect(getBundleStageLabel(" aligning ")).toBe("步骤 4/4：时间对齐中");
    expect(getBundleStageLabel("custom")).toBe("处理中（custom）");
    expect(getBundleStageLabel("")).toBe("处理中");
    expect(getBundleStageLabel(undefined)).toBe("处理中");
  });

  it("builds query error text from detail and nested fields", () => {
    expect(getBundleQueryErrorText({ detail: "bad request" }, 400)).toBe(
      "查询失败: bad request"
    );
    expect(
      getBundleQueryErrorText({ error: { message: "nested failure" } }, 500)
    ).toBe("查询失败: nested failure");
    expect(getBundleQueryErrorText({ error: "direct failure" }, 502)).toBe(
      "查询失败: direct failure"
    );
    expect(getBundleQueryErrorText({}, 503)).toBe("查询失败: 503");
    expect(getBundleQueryErrorText(null, 504)).toBe("查询失败: 504");
  });

  it("formats status details with optional fields", () => {
    const text = formatBundleStatusDetails({
      status: "aligning",
      progress: 0.41,
      file_count: 12,
      files_by_controller: { tbox: 3, mcu: 9 },
      error: "partial failure",
    });

    expect(text).toContain("状态: 步骤 4/4：时间对齐中");
    expect(text).toContain("阶段标识: aligning");
    expect(text).toContain("进度: 41%");
    expect(text).toContain("已分类文件: 12");
    expect(text).toContain("按控制器: tbox=3, mcu=9");
    expect(text).toContain("错误: partial failure");
  });

  it("hides stage identifier for terminal statuses", () => {
    const doneText = formatBundleStatusDetails({ status: "done" });
    const failedText = formatBundleStatusDetails({ status: "failed" });

    expect(doneText).toBe("状态: 处理完成");
    expect(failedText).toBe("状态: 处理失败");
  });
});
