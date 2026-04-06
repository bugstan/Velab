"""
WorkspaceManager 单元测试

覆盖场景：
1. 基础操作：create / read / append / cleanup
2. 并发安全：多 Agent 并行写入不丢数据
3. 降级场景：disabled 模式、磁盘满模拟
4. 归档功能：tar.gz 打包
5. section 隔离：各 Agent 写入不互相覆盖
6. todo 状态更新：checklist 打勾/取消

作者：FOTA 诊断平台团队
创建时间：2026-04-06
"""

import asyncio
import shutil
import tarfile
from pathlib import Path

import pytest
import pytest_asyncio

# 测试用的临时工作区基目录
TEST_BASE_DIR = Path(__file__).parent.parent / "data" / "_test_workspaces"
TEST_ARCHIVE_DIR = Path(__file__).parent.parent / "data" / "_test_workspaces_archive"


@pytest.fixture(autouse=True)
def clean_test_dirs():
    """每个测试前后清理测试目录"""
    if TEST_BASE_DIR.exists():
        shutil.rmtree(TEST_BASE_DIR)
    if TEST_ARCHIVE_DIR.exists():
        shutil.rmtree(TEST_ARCHIVE_DIR)
    yield
    if TEST_BASE_DIR.exists():
        shutil.rmtree(TEST_BASE_DIR)
    if TEST_ARCHIVE_DIR.exists():
        shutil.rmtree(TEST_ARCHIVE_DIR)


def _make_manager(**kwargs):
    """创建测试用的 WorkspaceManager 实例"""
    from services.workspace_manager import WorkspaceManager
    return WorkspaceManager(
        base_dir=TEST_BASE_DIR,
        archive_dir=TEST_ARCHIVE_DIR,
        **kwargs,
    )


# ── 1. 基础操作 ──


class TestCreate:
    def test_create_workspace_success(self):
        mgr = _make_manager()
        ctx = mgr.create("task-001", user_query="iCGM 挂死", scenario_id="fota-diagnostic")

        assert ctx is not None
        assert ctx.task_id == "task-001"
        assert ctx.workspace_dir.exists()
        assert ctx.focus_path.exists()
        assert ctx.notes_path.exists()
        assert ctx.todo_path.exists()

    def test_create_focus_contains_query(self):
        mgr = _make_manager()
        ctx = mgr.create("task-002", user_query="MPU 校验失败")

        content = ctx.focus_path.read_text()
        assert "MPU 校验失败" in content

    def test_create_idempotent(self):
        """重复创建同一 task_id 不报错"""
        mgr = _make_manager()
        ctx1 = mgr.create("task-003")
        ctx2 = mgr.create("task-003")

        assert ctx1 is not None
        assert ctx2 is not None

    def test_create_disabled_returns_none(self):
        mgr = _make_manager(enabled=False)
        ctx = mgr.create("task-disabled")

        assert ctx is None


class TestRead:
    def test_read_existing_file(self):
        mgr = _make_manager()
        ctx = mgr.create("task-read")
        content = mgr.read(ctx, "focus.md")

        assert content is not None
        assert "诊断任务总览" in content

    def test_read_nonexistent_file(self):
        mgr = _make_manager()
        ctx = mgr.create("task-read-missing")
        content = mgr.read(ctx, "nonexistent.md")

        assert content is None


class TestCleanup:
    def test_cleanup_removes_directory(self):
        mgr = _make_manager()
        ctx = mgr.create("task-cleanup")
        workspace_dir = ctx.workspace_dir

        assert workspace_dir.exists()
        mgr.cleanup("task-cleanup")
        assert not workspace_dir.exists()

    def test_cleanup_nonexistent_succeeds(self):
        mgr = _make_manager()
        result = mgr.cleanup("nonexistent-task")
        assert result is True

    def test_cleanup_with_archive(self):
        mgr = _make_manager()
        ctx = mgr.create("task-archive")
        # 写入一些内容
        (ctx.workspace_dir / "notes.md").write_text("Test note content")

        mgr.cleanup("task-archive", archive=True)

        # 工作区已删除
        assert not ctx.workspace_dir.exists()
        # 归档文件存在
        archive_path = TEST_ARCHIVE_DIR / "task-archive.tar.gz"
        assert archive_path.exists()
        # 验证归档内容
        with tarfile.open(archive_path, "r:gz") as tar:
            names = tar.getnames()
            assert any("notes.md" in n for n in names)


# ── 2. 并发安全 ──


class TestConcurrentAppend:
    @pytest.mark.asyncio
    async def test_parallel_writes_no_data_loss(self):
        """3 个 Agent 并行写入 notes.md，全部内容都应保留"""
        mgr = _make_manager()
        ctx = mgr.create("task-concurrent")

        async def write_agent(agent_name: str, n_writes: int):
            for i in range(n_writes):
                await mgr.append(
                    ctx, "notes.md", agent_name,
                    f"发现 #{i+1} from {agent_name}"
                )

        # 3 个 Agent 各写 5 条
        await asyncio.gather(
            write_agent("Log Analytics Agent", 5),
            write_agent("Jira Knowledge Agent", 5),
            write_agent("Doc Retrieval Agent", 5),
        )

        content = mgr.read(ctx, "notes.md")
        assert content is not None

        # 验证所有 Agent 的 section 都存在
        assert "## Log Analytics Agent" in content
        assert "## Jira Knowledge Agent" in content
        assert "## Doc Retrieval Agent" in content

        # 验证没有数据丢失 (每个 Agent 5 条记录)
        for agent in ["Log Analytics Agent", "Jira Knowledge Agent", "Doc Retrieval Agent"]:
            for i in range(1, 6):
                assert f"发现 #{i} from {agent}" in content


# ── 3. Section 隔离 ──


class TestSectionIsolation:
    @pytest.mark.asyncio
    async def test_different_sections_isolated(self):
        mgr = _make_manager()
        ctx = mgr.create("task-isolation")

        await mgr.append(ctx, "notes.md", "Agent A", "A 的发现 1")
        await mgr.append(ctx, "notes.md", "Agent B", "B 的发现 1")
        await mgr.append(ctx, "notes.md", "Agent A", "A 的发现 2")

        content = mgr.read(ctx, "notes.md")

        # 两个 section 分别存在
        assert "## Agent A" in content
        assert "## Agent B" in content

        # 各自的内容都保留
        assert "A 的发现 1" in content
        assert "A 的发现 2" in content
        assert "B 的发现 1" in content


# ── 4. 降级场景 ──


class TestDegradation:
    def test_capacity_exceeded_returns_none(self):
        """容量超限时 create 返回 None（降级）"""
        mgr = _make_manager(max_total_size_mb=0)  # 0MB 立即超限
        # 先创造一个文件使 base_dir 非空
        TEST_BASE_DIR.mkdir(parents=True, exist_ok=True)
        (TEST_BASE_DIR / "dummy.txt").write_text("x" * 100)

        ctx = mgr.create("task-exceeded")
        assert ctx is None

    @pytest.mark.asyncio
    async def test_append_to_nonexistent_workspace(self):
        """写入不存在的 workspace 应返回失败而非抛异常"""
        mgr = _make_manager()
        # 不调用 create，直接构造一个无效的 ctx
        from services.workspace_manager import WorkspaceContext
        fake_ctx = WorkspaceContext(
            task_id="fake",
            workspace_dir=Path("/tmp/nonexistent_ws_test"),
        )
        result = await mgr.append(fake_ctx, "notes.md", "Agent X", "content")
        assert result is False


# ── 5. TODO 状态更新 ──


class TestTodoUpdate:
    @pytest.mark.asyncio
    async def test_mark_item_completed(self):
        from services.tool_functions import update_todo_status

        mgr = _make_manager()
        ctx = mgr.create("task-todo")

        result = await update_todo_status(
            str(ctx.workspace_dir), "日志阶段验证", completed=True
        )

        assert result["success"] is True
        content = ctx.todo_path.read_text()
        assert "[x] 日志阶段验证" in content

    @pytest.mark.asyncio
    async def test_mark_item_uncompleted(self):
        from services.tool_functions import update_todo_status

        mgr = _make_manager()
        ctx = mgr.create("task-todo-undo")

        # 先标记完成
        await update_todo_status(str(ctx.workspace_dir), "日志阶段验证", completed=True)
        # 再取消
        result = await update_todo_status(str(ctx.workspace_dir), "日志阶段验证", completed=False)

        assert result["success"] is True
        content = ctx.todo_path.read_text()
        assert "[ ] 日志阶段验证" in content

    @pytest.mark.asyncio
    async def test_missing_item_returns_failure(self):
        from services.tool_functions import update_todo_status

        mgr = _make_manager()
        ctx = mgr.create("task-todo-miss")

        result = await update_todo_status(
            str(ctx.workspace_dir), "不存在的排查项", completed=True
        )
        assert result["success"] is False


# ── 6. 统计信息 ──


class TestStats:
    def test_stats_reports_active_count(self):
        mgr = _make_manager()
        mgr.create("task-stats-1")
        mgr.create("task-stats-2")

        stats = mgr.get_stats()
        assert stats["active_workspaces"] == 2
        assert stats["enabled"] is True
        assert stats["total_size_mb"] >= 0  # 模板文件极小，round 后可能为 0.0
        assert stats["max_size_mb"] == 1024
