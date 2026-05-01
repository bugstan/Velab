import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@/__tests__/utils/test-utils";
import UploadSummaryCard from "@/components/UploadSummaryCard";

const baseSummary = {
  bundleId: "bundle-1",
  fileName: "vehicle_logs.zip",
  fileCount: 4,
  filesByController: { tbox: 2, mcu: 2 },
  validTimeRangeByController: {
    tbox: { start: 1712044800, end: 1712048400 },
    mcu: { start: 1712044860, end: 1712048300 },
  },
};

describe("UploadSummaryCard", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [],
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("应该渲染本地时区信息与基础统计", async () => {
    render(<UploadSummaryCard summary={baseSummary} />);

    expect(screen.getByText(/上传 Summary/)).toBeInTheDocument();
    expect(screen.getByText(/拖拽时间轴以 brush 缩放/)).toBeInTheDocument();
    expect(screen.getByText(/时区：/)).toBeInTheDocument();
    expect(screen.getByText(/共 4 个文件/)).toBeInTheDocument();
    expect(screen.getByText(/2 类日志/)).toBeInTheDocument();

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(1);
    });
  });

  it("应支持拖拽 brush 生成缩放窗口", async () => {
    render(<UploadSummaryCard summary={baseSummary} />);
    const track = await screen.findByTestId("summary-brush-track");

    Object.defineProperty(track, "getBoundingClientRect", {
      value: () => ({
        left: 0,
        top: 0,
        width: 200,
        height: 32,
        right: 200,
        bottom: 32,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }),
    });

    fireEvent.mouseDown(track, { clientX: 20 });
    fireEvent.mouseMove(window, { clientX: 150 });
    fireEvent.mouseUp(window);

    expect(screen.getByTestId("summary-brush-selection")).toBeInTheDocument();
    expect(screen.getByText("重置")).toBeInTheDocument();
  });

  it("应支持绝对时间与相对时间切换", async () => {
    render(<UploadSummaryCard summary={baseSummary} />);

    const relativeButton = screen.getByRole("button", { name: "相对时间(Δt)" });
    fireEvent.click(relativeButton);

    await waitFor(() => {
      expect(screen.getAllByText(/Δ\d/).length).toBeGreaterThan(0);
    });
  });

  it("应在密集事件时显示聚合标记", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ([
        { event_id: "e1", controller: "tbox", event_type: "reboot", aligned_timestamp: 1712048340 },
        { event_id: "e2", controller: "tbox", event_type: "reboot", aligned_timestamp: 1712048345 },
        { event_id: "e3", controller: "tbox", event_type: "boot", aligned_timestamp: 1712048350 },
      ]),
    }));

    render(<UploadSummaryCard summary={baseSummary} />);

    await waitFor(() => {
      expect(screen.getByText("+3")).toBeInTheDocument();
    });
  });
});
