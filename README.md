# mini_agent_core

**从零手写的轻量级 Agent 框架**，~500 行核心代码，不依赖任何 LLM 框架。

> 核心是一个 ReAct 循环，外加流式输出、多 Agent 辩论、Trace 可视化。看清 Agent 本质的最小可运行代码。

---

## 目录

- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [核心模块](#核心模块)
- [运行 Demo](#运行-demo)
- [API 使用](#api-使用)
- [特性](#特性)
- [测试](#测试)

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-你的key

# 3. 跑起来
python demo/reasoning.py        # 基础推理
python demo/reasoning_stream.py # 流式打字机
python demo/chat.py             # 交互式对话
```

---

## 项目结构

```
mini_agent_core/
├── core/                        # 框架核心（~500 行）
│   ├── llm.py                   # LLM 调用层（同步 + 流式 SSE）
│   ├── tools.py                 # 工具注册 + 自动 JSON Schema
│   ├── agent.py                 # ReAct 循环引擎
│   ├── memory.py                # 短期记忆 + 长期记忆
│   ├── debate.py                # 多 Agent 辩论编排
│   └── trace.py                 # Trace → HTML 可视化导出
│
├── demo/                        # 演示入口
│   ├── reasoning.py             # 基础多步推理
│   ├── reasoning_stream.py      # 流式推理
│   ├── chat.py                  # 交互式 CLI 对话
│   ├── debate_demo.py           # 三 Agent 辩论
│   └── export_demo.py           # 导出 HTML 报告
│
├── tests/                       # 35 个单元测试
├── output/                      # 生成的 HTML 报告（gitignore）
├── .env.example                 # 环境变量模板
└── requirements.txt             # 4 个依赖
```

---

## 核心模块

### llm.py — LLM 调用层

用 `httpx` 直调 DeepSeek API，不套 OpenAI SDK。展示对 HTTP 协议和 function calling 协议的底层理解。

```python
from core.llm import LLM, LLMConfig

llm = LLM(LLMConfig(api_key="sk-xxx", model="deepseek-chat"))

# 同步调用
response = llm.chat([{"role": "user", "content": "1+1=?"}])
print(response.content)  # "2"

# 流式调用
for chunk in llm.chat_stream([...]):
    print(chunk.content, end="", flush=True)  # 逐字输出
```

### tools.py — 工具注册系统

装饰器模式 + 类型反射，从函数签名自动推断 JSON Schema，无需手写参数定义。

```python
from core.tools import tool

@tool(description="计算数学表达式")
def calculate(expression: str) -> float:
    """计算数学表达式

    Args:
        expression: 数学表达式字符串
    """
    return eval(expression)
```

自动生成 LLM function calling 所需的完整 JSON Schema。

### agent.py — ReAct 循环引擎

整个框架的核心。一个 `for` 循环实现完整的 Reasoning + Acting：

```
User 输入 → Thought → Action(调工具) → Observation → Thought → ... → Final Answer
```

```python
from core.agent import Agent

agent = Agent(llm=llm, tools=[calculate, search], max_iterations=10)
result = agent.run("光从太阳到地球要多久？")

print(result.content)    # 最终答案
print(result.trace)      # 完整推理轨迹
print(result.usage)      # Token 用量
```

**每轮 LLM 返回两种结果：要么要求调工具 → 执行后继续循环；要么给出最终答案 → 结束。** 核心逻辑 ~30 行。

### memory.py — 记忆系统

| 类 | 存储 | 特点 |
|----|------|------|
| `SlidingWindowMemory` | 最近 N 条对话 | 内存，窗口满自动丢弃 |
| `LongTermMemory` | ChromaDB 向量库 | 落磁盘，跨对话语义检索 |

### debate.py — 多 Agent 辩论

外挂在 ReAct 上的编排层：多个 Agent 共享上下文，轮流发言，互相质疑。

```
Solver(求解) → Critic(挑刺) → Judge(裁决) → 最终答案
```

```python
from core.debate import Debate

debate = Debate(solver=agent_a, critic=agent_b, judge=agent_c)
result = debate.run("地球绕太阳的线速度是多少？")
```

### trace.py — 可视化导出

将推理轨迹渲染为自包含 HTML 页面，双击即开，支持折叠/展开、token 统计。

```python
from core.trace import export_trace

export_trace(result, "output/trace.html", question="...")
```

---

## 运行 Demo

```bash
# 基础多步推理
python demo/reasoning.py

# 流式打字机效果
python demo/reasoning_stream.py

# 交互式 CLI（支持 /trace /export /clear /exit）
python demo/chat.py

# 三 Agent 辩论
python demo/debate_demo.py

# 导出 HTML 报告
python demo/export_demo.py           # Agent trace
python demo/export_demo.py debate    # Debate trace
```

---

## API 使用

```python
from core.llm import LLM, LLMConfig
from core.tools import tool
from core.agent import Agent

# 定义工具
@tool(description="计算数学表达式")
def calculate(expression: str) -> float:
    return eval(expression)

@tool(description="搜索知识库")
def search(query: str) -> str:
    knowledge = {"光速": "3×10⁸ m/s", ...}
    return knowledge.get(query, "未找到")

# 创建 Agent
llm = LLM(LLMConfig(api_key="sk-xxx"))
agent = Agent(llm=llm, tools=[calculate, search])

# 推理
result = agent.run("太阳光到地球要多久？")
print(result.content)   # 约 8.31 分钟
print(result.iterations) # 2
print(result.usage)      # {prompt_tokens: ..., completion_tokens: ...}

# 流式推理
for event in agent.run_stream("1+1=?"):
    if event["type"] == "thought_chunk":
        print(event["text"], end="", flush=True)
```

---

## 特性

| 特性 | 说明 |
|------|------|
| 🔧 **httpx 直调** | 不套 SDK，展示 HTTP 层和 function calling 协议 |
| 🎯 **类型反射 Schema** | 从函数签名自动推断 JSON Schema |
| 🛡️ **异常安全** | 工具出错返回错误信息，不崩溃 |
| 📋 **完整 Trace** | Thought → Action → Observation 全记录 |
| ⚡ **流式输出** | SSE 逐字吐出，打字机效果 |
| ⚔️ **多 Agent 辩论** | Solver·Critic·Judge 三方互搏 |
| 📊 **可视化导出** | 一键 HTML，浏览器即开即用 |
| 🏷️ **钩子系统** | on_tool_call / on_final 可扩展 |

---

## 测试

```bash
pytest tests/ -v          # 35 tests
```

覆盖：LLM 响应解析、Agent ReAct 循环、工具注册/Schema 生成、记忆系统。
