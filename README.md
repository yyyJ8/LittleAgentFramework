# mini_agent_core

从零手写 Agent 核心循环，展示对 Agent 底层原理的理解。

---

## 是什么

一个轻量级的 Agent 核心库，约 400 行 Python，核心是一个 ReAct 循环。

**不是框架。** 它是让你看清 Agent 本质的最小可运行代码——没有 IoC 容器、没有配置驱动引擎、没有花哨的编排抽象。就是 tool calling + 循环 + 记忆。

## 结构

```
mini_agent_core/
├── core/
│   ├── __init__.py      # 统一导出
│   ├── llm.py           # httpx 直调 LLM API + 流式 SSE
│   ├── tools.py         # @tool 装饰器 + 自动 JSON Schema
│   ├── memory.py        # 短期滑动窗口 + 长期向量检索
│   ├── agent.py         # ReAct 循环 + 流式推理
│   ├── debate.py        # 多 Agent 辩论编排
│   └── trace.py         # Trace → HTML 可视化导出
├── demo/
│   ├── reasoning.py           # 多步推理演示
│   ├── reasoning_stream.py    # 流式打字机效果
│   ├── debate_demo.py         # 三 Agent 辩论
│   └── export_demo.py         # 导出交互式 HTML 报告
├── tests/
│   ├── test_agent.py
│   ├── test_llm.py
│   ├── test_memory.py
│   └── test_tools.py
└── requirements.txt
```

## 安装

```bash
pip install -r requirements.txt
cp .env.example .env   # 编辑 .env 填入 DEEPSEEK_API_KEY
```

## 快速使用

```python
from core import LLM, LLMConfig, Agent
from core.tools import tool

# 1. 定义工具
@tool(description="计算数学表达式")
def calculate(expression: str) -> float:
    return eval(expression)

# 2. 创建 Agent
llm = LLM(LLMConfig(api_key="your-key"))
agent = Agent(llm=llm, tools=[calculate])

# 3. 运行
result = agent.run("计算 (3+5)*2")
print(result.content)   # → 16
print(result.trace)     # → 完整推理轨迹
```

## 运行演示

```bash
# 基础推理
python demo/reasoning.py

# 流式打字机效果
python demo/reasoning_stream.py

# 多 Agent 辩论
python demo/debate_demo.py

# 导出交互式 HTML 报告
python demo/export_demo.py           # Agent trace
python demo/export_demo.py debate    # Debate trace
```

## 测试

```bash
pytest tests/ -v          # 35 tests
```

## 核心逻辑

ReAct 循环核心约 30 行：

```python
def run(self, user_input: str) -> AgentResult:
    messages = self._build_context(user_input)

    for i in range(self.max_iterations):
        response = self.llm.chat(messages, tools=ToolRegistry.schemas())

        if response.tool_calls:
            for tc in response.tool_calls:
                obs = tool.execute(**tc.arguments)
                messages.append({"role": "tool", ...})
            continue

        if response.content:
            return AgentResult(content=response.content)

    raise MaxIterationsError()
```

## 特性

| 特性 | 说明 |
|------|------|
| 🔧 **httpx 直调** | 不套 SDK，展示 HTTP 层和 function calling 协议 |
| 🎯 **类型反射 Schema** | 从函数签名自动推断 JSON Schema |
| 🛡️ **异常安全** | 工具调用出错返回错误信息而非崩溃 |
| 📋 **完整 Trace** | thought → action → observation 轨迹，可审计可调试 |
| ⚡ **流式输出** | SSE 逐字吐出，打字机效果 |
| ⚔️ **多 Agent 辩论** | Solver·Critic·Judge 三方辩论，共享上下文 |
| 📊 **可视化导出** | 一键导出交互式 HTML 报告，浏览器即开即用 |
