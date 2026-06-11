# mini_agent_core — 实现方案

## 核心理念

> **展示你对 Agent 原理的深度理解，而不是框架工程上的广度。**

| 不做 | 做 |
|---|---|
| IoC 容器 / Runtime | **干净的 ReAct 循环**（20-30 行核心逻辑） |
| Provider 抽象体系 | **httpx 直调 API**，展示 HTTP 层理解 |
| Pipeline 步骤引擎 | **类型反射 + 自动 schema 生成**，展示对 function calling 的理解 |
| YAML 配置驱动 | **可扩展的记忆系统**（短期窗口 + 长期向量） |
| "我写了个框架" | **"我懂 Agent 最底层的原理"** |

---

## 目录结构

```
mini_agent_core/
├── core/
│   ├── __init__.py
│   ├── llm.py          # LLM 调用封装（httpx → DeepSeek）
│   ├── tools.py        # @tool 装饰器 + schema 自动生成
│   ├── memory.py       # 短期记忆（滑动窗口）+ 长期记忆（ChromaDB）
│   └── agent.py        # ReAct 循环核心 ★
├── demo/
│   └── reasoning.py    # 多步推理演示
├── tests/
│   ├── test_llm.py
│   ├── test_tools.py
│   ├── test_memory.py
│   └── test_agent.py
└── requirements.txt
```

> **为什么没有 orchestrator？** — 编排器属于应用层，不是 Agent 原理的一部分。面试时可用话术带过："多 Agent 编排是应用层逻辑，用 concurrent.futures 就能实现，核心是对 ReAct 循环的理解"。

---

## 模块设计

### 1. `core/llm.py` — LLM 调用层

**定位**：展示你对 API 协议的底层理解，不套 SDK。

```python
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[ToolCall] | None
    usage: dict  # token 用量

class LLM:
    def __init__(self, config: LLMConfig): ...
    
    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        """用 httpx 发送 POST /v1/chat/completions"""
```

**关键设计**：
- 用 `httpx` 直接发 HTTP 请求，展示 HTTP 层理解
- 手动解析 response，提取 tool_calls（JSON 解析）
- 内置重试（指数退避）、超时、错误处理
- 支持 OpenAI 兼容格式（DeepSeek 原生兼容）

### 2. `core/tools.py` — 工具注册系统

**定位**：展示你对类型系统和 function calling schema 的理解。

```python
# 用户侧代码
@tool(description="计算数学表达式的值")
def calculate(expression: str) -> float:
    """计算表达式，如 "3 + 5 * 2" 返回 13.0"""
    return eval(expression)  # 安全沙箱中实际用 numexpr 或 ast

@tool(description="搜索常识知识")
def search_knowledge(query: str) -> str:
    """返回与查询相关的常识信息"""
    ...

# 自动生成 LLM 需要的 tool schema
# [{
#   "type": "function",
#   "function": {
#     "name": "calculate",
#     "description": "计算数学表达式的值",
#     "parameters": {
#       "type": "object",
#       "properties": {
#         "expression": {"type": "string", "description": "如 "3 + 5 * 2""}
#       },
#       "required": ["expression"]
#     }
#   }
# }]
```

```python
class Tool:
    name: str
    description: str
    func: Callable
    parameters: dict       # JSON Schema
    
    def execute(self, **kwargs) -> str:
        """执行工具，异常安全，返回字符串结果"""

class ToolRegistry:
    """全局注册表，支持 @tool 装饰器注册"""
    
    @classmethod
    def register(cls, func, name=None, description=None): ...
    @classmethod
    def get(cls, name) -> Tool: ...
    @classmethod
    def schemas(cls) -> list[dict]: ...  # 给 LLM 用
```

**关键设计**：
- `inspect.signature()` + `typing.get_type_hints()` 解析参数
- 类型 → JSON Schema 映射：`int→integer`, `float→number`, `str→string`, `bool→boolean`, `Optional→nullable`
- 自动提取函数名和文档字符串
- `execute()` 统一返回字符串（LLM 需要的格式）

### 3. `core/memory.py` — 记忆系统

**定位**：短期 + 长期记忆，展示对 Agent 记忆管理的理解。

```python
class SlidingWindow:
    """短期记忆：维护消息列表，超 window_size 自动丢弃最早"""
    
    def __init__(self, window_size: int = 20): ...
    def add(self, message: dict): ...
    def get_context(self) -> list[dict]: ...
    def clear(self): ...

class LongTermMemory:
    """长期记忆：ChromaDB 向量检索"""
    
    def __init__(self, persist_dir: str = "~/.agent_memory"): ...
    def store(self, key: str, content: str, metadata: dict = {}): ...
    def query(self, question: str, top_k: int = 5) -> list[str]: ...
```

**关键设计**：
- `SlidingWindow` — 纯粹的列表管理，无外部依赖
- `LongTermMemory` — 可选组件，ChromaDB 持久化
- embedding 用 ChromaDB 默认的 all-MiniLM-L6-v2（自动下载）
- 两者都实现相同的 `add/query` 接口，可替换

### 4. `core/agent.py` — ReAct 循环（核心亮点）

**定位**：整个项目的灵魂。干净、正确、有边界处理的 ReAct 循环。

```python
@dataclass
class AgentResult:
    content: str
    trace: list[dict]   # 完整 thought→action→observation 轨迹
    usage: dict
    iterations: int

class Agent:
    def __init__(
        self,
        llm: LLM,
        tools: list[Tool],
        system_prompt: str | None = None,
        max_iterations: int = 10,
    ): ...
    
    def run(self, user_input: str) -> AgentResult:
        """ReAct 循环主入口"""
```

**ReAct 循环核心逻辑（约 25 行）**：

```python
def run(self, user_input: str) -> AgentResult:
    messages = self._build_context(user_input)
    
    for i in range(self.max_iterations):
        response = self.llm.chat(messages, tools=ToolRegistry.schemas())
        
        # 情况 1：LLM 返回 Final Answer
        if response.content:
            # 检查是否有隐含的 Final Answer 标记
            if "[FINAL]" in response.content or not response.tool_calls:
                return AgentResult(content=response.content, ...)
        
        # 情况 2：LLM 请求调用工具
        if response.tool_calls:
            for tc in response.tool_calls:
                tool = ToolRegistry.get(tc.name)
                observation = tool.execute(**tc.arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": observation
                })
    
    raise MaxIterationsError(f"超过 {self.max_iterations} 轮未得出最终答案")
```

**提示词设计（至关重要）**：

```
你是一个擅长多步推理的 AI 助手。你有以下工具可以使用：
{tool_descriptions}

请按以下格式思考和回答：

Thought: 分析当前情况，决定下一步做什么
Action: 工具名称
Action Input: {{"参数名": "参数值"}}

...（可多次重复 Thought → Action → Observation 步骤）

Thought: 我已经得到足够信息
Final Answer: [FINAL] 最终回答
```

**关键设计**：
- 核心循环控制在 25 行左右，一目了然
- 同时支持 function calling + 纯文本 ReAct 两种模式（兼容不同 LLM）
- 记录完整 trace 供面试演示和调试
- 有最大轮次保护，不会无限循环

---

## 面试 Demo 设计

### `demo/reasoning.py` — 多步推理演示

不搞简单的计算器，而是展示 **chain-of-thought + tool use** 的完整过程。

```python
def main():
    llm = LLM(config)
    
    @tool(description="计算数学表达式")
    def calculate(expression: str) -> float:
        return eval(expression)
    
    @tool(description="搜索常识知识")
    def search_knowledge(query: str) -> str:
        knowledge = {
            "光速": "光速约为每秒 299,792,458 米",
            "地球到太阳距离": "约 1.496 亿公里（1 个天文单位）",
            ...
        }
        return knowledge.get(query, "未找到相关信息")
    
    agent = Agent(llm=llm, tools=[calculate, search_knowledge])
    
    # 演示：多步推理问题
    result = agent.run(
        "光从太阳到地球需要多长时间？"
        "已知：光速约 3×10⁸ 米/秒，地球到太阳约 1.496×10¹¹ 米"
    )
    
    print("最终答案:", result.content)
    print("\n推理轨迹:")
    for step in result.trace:
        print(f"  Thought: {step['thought']}")
        print(f"  Action: {step['tool_call']}")
        print(f"  Observation: {step['observation']}")
```

**预期输出效果**：

```
Thought: 要计算光从太阳到地球的时间，我需要用距离除以速度。
        距离 = 1.496×10¹¹ 米，速度 = 3×10⁸ 米/秒
Action: calculate
Action Input: {"expression": "1.496e11 / 3e8"}
Observation: 498.666...

Thought: 得到约 498.67 秒，换算成分钟是 498.67 / 60
Action: calculate
Action Input: {"expression": "498.6666666666667 / 60"}
Observation: 8.311...

Final Answer: [FINAL] 光从太阳到地球大约需要 8.31 分钟（约 498.67 秒）
```

---

## 实现阶段

### Phase 1：LLM + Tools（1 天）

文件创建顺序：
1. `requirements.txt` — httpx, chromadb, pydantic, pytest
2. `core/__init__.py` — 统一导出
3. `core/llm.py` — LLM 类，能调通 DeepSeek
4. `core/tools.py` — @tool 装饰器 + ToolRegistry

验证：
```bash
python -c "
from mini_agent_core.core.tools import tool, ToolRegistry

@tool(description='计算器')
def calculate(expr: str) -> float:
    return eval(expr)

print(ToolRegistry.schemas())
# 应输出正确的 JSON Schema
"
```

### Phase 2：Agent + 记忆（2 天）

5. `core/memory.py` — SlidingWindow + LongTermMemory
6. `core/agent.py` — ReAct 循环（核心 25 行）
7. `tests/test_agent.py` — 单元测试

验证：跑通多步推理 demo

### Phase 3：Demo + 测试（1 天）

8. `demo/reasoning.py` — 多步推理演示
9. `tests/` 补全 — 至少覆盖每个模块的核心路径
10. 异常处理 hardening

验证：
```bash
python demo/reasoning.py
# 输出完整的推理轨迹
```

---

## 面试话术（怎么讲）

> "这是我手写的 Agent 核心，核心是 25 行的 ReAct 循环。
> 不用 LangGraph 是因为我想展示我对 Agent 原理的底层理解——
> LLM 调用层我用 httpx 直接调协议，工具注册用类型反射自动生成 schema，
> 记忆系统分短期滑动窗口和长期向量检索。
> 面试官你看中框架应用能力可以看我的 AI 面试官项目，
> 想看底层原理看这个——两者互补。"

---

## 依赖

```txt
httpx>=0.27.0
chromadb>=0.5.0
pydantic>=2.0.0
pytest>=8.0.0
```

> ChromaDB 自带 all-MiniLM-L6-v2 embedding，无需额外装 sentence-transformers。
> 如果 DeepSeek 支持 function calling（版本 v4 应该支持），优先用它返回的结构化 tool_calls；
> 如果不支持，回退到纯文本 ReAct 格式解析。
