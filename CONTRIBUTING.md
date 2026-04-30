# 贡献指南

欢迎参与 My Agent 的开发！以下是三种最常见的贡献方式。

---

## 添加 MCP 工具

### 1. 新建 server 文件

在 `backend/mcp_servers/` 下创建 `<name>.py`，仿照现有 server（如 `bocha_search.py`）：

```python
from __future__ import annotations

class MyServer:
    def __init__(self) -> None: ...

    async def my_action(self, param: str) -> dict:
        ...
```

工具名称格式：`{server}_{method}`（下划线，符合 OpenAI function name 规范）。

### 2. 注册到 ToolRegistry

在 `backend/orchestrator/tools.py` 的 `ToolRegistry.__init__` 里注册：

```python
self._servers["myserver"] = MyServer()
self._register_tool(
    name="myserver_my_action",
    description="...",
    parameters={
        "type": "object",
        "properties": {"param": {"type": "string", "description": "..."}},
        "required": ["param"],
    },
    server="myserver",
    method="my_action",
)
```

### 3. 写测试

在 `tests/smoke_test.py` 中新增测试类，使用 `monkeypatch` 桩住网络调用：

```python
class TestMyServer:
    def test_my_action_returns_dict(self):
        from backend.mcp_servers.my_server import MyServer
        import asyncio
        server = MyServer()
        result = asyncio.run(server.my_action("test"))
        assert isinstance(result, dict)
```

### 4. 更新人格工具白名单（可选）

在 `personas/<name>/tools.yaml` 的 `allowed` 列表里加上 `myserver_*`。

---

## 创建人格包

详细步骤见 [docs/persona-guide.md](docs/persona-guide.md)，简要流程：

1. `cp -r personas/_template personas/<Name>`
2. 编辑 `system.jinja2`（性格、口头禅、禁忌）
3. 准备 10–30 秒干净参考音 → `voices/ref.wav`，对应文字 → `voice_ref.txt`
4. 调整 `tools.yaml` 工具权限
5. 打包验证：`python tools/persona_pack.py pack personas/<Name>`

---

## Bug 修复 / 功能改进

### 提交前检查

```bash
# 全量 smoke test 必须通过
python -m pytest tests/smoke_test.py -v

# 新功能请同步新增测试（至少覆盖 happy path + 一个边界情况）
```

### Commit 格式

项目使用中文 `主题：详情` 格式：

```
修复：修正 critic_node 首词误判 "noted" 导致 persona 一致性检查失败
功能：新增 pyncm 歌词获取工具
重构：把 MainGraphState 从 dataclass 改为 TypedDict
```

### 代码风格

- 每个 Python 文件第一行：`from __future__ import annotations`
- 异步优先：所有 I/O 用 `async/await`
- 外部边界用 Pydantic v2（`model_dump()` / `model_validate()`），内部结构用 `dataclasses`
- 持久化用 SQLite（WAL 模式）
- 注释只写**为什么**，不写**做了什么**

---

## 文件结构速查

```
backend/mcp_servers/   ← MCP 工具实现
backend/orchestrator/  ← LangGraph 流水线 + ToolRegistry
core/persona.py        ← 人格加载逻辑
personas/              ← 人格定义目录
tools/persona_pack.py  ← 人格打包 CLI
tests/smoke_test.py    ← 257 个冒烟测试（全绿）
eval/                  ← 评测框架（YAML cases + judge ensemble）
```
