# API测试文档

## 概述

本目录包含FOTA智能诊断平台的API单元测试和集成测试。

## 测试结构

```
tests/
├── conftest.py              # 测试配置和fixtures
├── test_api_cases.py        # Cases API测试
├── test_api_parse.py        # Parse API测试
├── test_api_events.py       # Events API测试
└── test_integration.py      # 集成测试
```

## 测试覆盖

### 1. Cases API测试 (`test_api_cases.py`)

- ✅ 创建案例
- ✅ 创建重复案例（错误处理）
- ✅ 获取案例详情
- ✅ 获取不存在的案例（404）
- ✅ 列出案例
- ✅ 带过滤条件的案例列表
- ✅ 分页功能
- ✅ 删除案例
- ✅ 删除不存在的案例（404）

**测试数量**: 9个测试

### 2. Parse API测试 (`test_api_parse.py`)

- ✅ 提交解析任务
- ✅ 提交任务 - 案例不存在（404）
- ✅ 提交任务 - 无文件可解析（400）
- ✅ 提交任务 - 带时间窗口
- ✅ 查询任务状态
- ✅ 时间对齐
- ✅ 时间对齐 - 案例不存在（404）
- ✅ 时间对齐 - 无事件（400）

**测试数量**: 8个测试

### 3. Events API测试 (`test_api_events.py`)

- ✅ 查询事件
- ✅ 带过滤条件的事件查询
- ✅ 带时间范围的事件查询
- ✅ 关键词搜索
- ✅ 分页功能
- ✅ 获取单个事件
- ✅ 获取不存在的事件（404）
- ✅ 获取案例统计摘要
- ✅ 获取不存在案例的摘要（404）
- ✅ 导出事件为JSON
- ✅ 导出事件为CSV
- ✅ 带过滤条件的导出
- ✅ 导出不存在案例的事件（404）

**测试数量**: 13个测试

### 4. 集成测试 (`test_integration.py`)

- ✅ 完整工作流程（创建→上传→解析→查询→导出）
- ✅ 案例生命周期
- ✅ 并发案例创建
- ✅ 错误处理

**测试数量**: 4个测试

**总计**: 34个测试

## 运行测试

### 方法1: 使用pytest直接运行

```bash
cd backend

# 运行所有测试
pytest tests/ -v

# 运行特定测试文件
pytest tests/test_api_cases.py -v

# 运行特定测试类
pytest tests/test_api_cases.py::TestCasesAPI -v

# 运行特定测试方法
pytest tests/test_api_cases.py::TestCasesAPI::test_create_case -v
```

### 方法2: 使用测试脚本

```bash
cd backend
python run_tests.py
```

### 方法3: 带覆盖率报告

```bash
cd backend
pytest tests/ --cov=api --cov=models --cov=database --cov-report=html
```

查看覆盖率报告:
```bash
open htmlcov/index.html
```

## 测试配置

### Fixtures

测试使用以下共享fixtures（定义在`conftest.py`）:

- **test_db**: 测试数据库会话（内存SQLite）
- **client**: FastAPI测试客户端
- **sample_case**: 示例案例数据
- **sample_log_file**: 示例日志文件数据
- **sample_events**: 示例事件数据（5个事件）
- **mock_task_client**: Mock任务客户端（避免依赖Redis）

### 测试数据库

测试使用内存SQLite数据库，每个测试函数使用独立的数据库实例，确保测试隔离。

## 测试最佳实践

### 1. 测试命名

```python
def test_<功能>_<场景>():
    """测试描述"""
    pass
```

示例:
- `test_create_case()` - 测试创建案例
- `test_create_case_duplicate()` - 测试创建重复案例
- `test_get_case_not_found()` - 测试获取不存在的案例

### 2. 测试结构（AAA模式）

```python
def test_example(client, sample_case):
    # Arrange - 准备测试数据
    case_id = sample_case.case_id
    
    # Act - 执行操作
    response = client.get(f"/api/cases/{case_id}")
    
    # Assert - 验证结果
    assert response.status_code == 200
    assert response.json()["case_id"] == case_id
```

### 3. 使用Fixtures

```python
@pytest.fixture
def custom_case(test_db):
    """自定义fixture"""
    case = Case(case_id="custom_001", ...)
    test_db.add(case)
    test_db.commit()
    return case

def test_with_custom_fixture(client, custom_case):
    """使用自定义fixture的测试"""
    response = client.get(f"/api/cases/{custom_case.case_id}")
    assert response.status_code == 200
```

## 持续集成

### GitHub Actions示例

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        cd backend
        pip install -r requirements.txt
        pip install pytest pytest-cov
    
    - name: Run tests
      run: |
        cd backend
        pytest tests/ -v --cov=api --cov=models
```

## 故障排查

### 问题1: 导入错误

**症状**: `ModuleNotFoundError: No module named 'xxx'`

**解决**:
```bash
# 确保在backend目录下运行
cd backend

# 安装依赖
pip install -r requirements.txt

# 安装测试依赖
pip install pytest pytest-cov
```

### 问题2: 数据库错误

**症状**: 数据库连接或表不存在错误

**解决**: 测试使用内存SQLite，不需要真实数据库。检查`conftest.py`中的`test_db` fixture是否正确创建表。

### 问题3: Fixture未找到

**症状**: `fixture 'xxx' not found`

**解决**: 确保`conftest.py`在tests目录下，pytest会自动加载。

## 添加新测试

### 1. 创建新测试文件

```python
# tests/test_api_new.py
"""
New API 单元测试
"""

import pytest
from fastapi.testclient import TestClient

class TestNewAPI:
    """New API测试类"""
    
    def test_new_endpoint(self, client: TestClient):
        """测试新端点"""
        response = client.get("/api/new/endpoint")
        assert response.status_code == 200
```

### 2. 添加新Fixture

```python
# tests/conftest.py
@pytest.fixture
def new_fixture(test_db):
    """新fixture"""
    # 创建测试数据
    data = ...
    test_db.add(data)
    test_db.commit()
    return data
```

### 3. 运行新测试

```bash
pytest tests/test_api_new.py -v
```

## 测试报告

### 生成HTML报告

```bash
pytest tests/ --html=report.html --self-contained-html
```

### 生成JUnit XML报告

```bash
pytest tests/ --junitxml=junit.xml
```

## 性能测试

### 使用pytest-benchmark

```bash
pip install pytest-benchmark

# 在测试中使用
def test_performance(benchmark, client):
    result = benchmark(client.get, "/api/cases")
    assert result.status_code == 200
```

## 相关文档

- [Pytest文档](https://docs.pytest.org/)
- [FastAPI测试](https://fastapi.tiangolo.com/tutorial/testing/)
- [SQLAlchemy测试](https://docs.sqlalchemy.org/en/14/orm/session_transaction.html#joining-a-session-into-an-external-transaction-such-as-for-test-suites)
