# mini_agent_core

从零手写 Agent 核心循环，展示对 Agent 底层原理的理解。

> 与 AI 面试官项目互补：一个偏应用（完整业务系统），一个偏底层（Agent 原理）。

---

## 是什么

一个轻量级的 Agent 核心库，约 400 行 Python，核心是一个 ReAct 循环。

**不是框架。** 它是让你看清 Agent 本质的最小可运行代码——没有 IoC 容器、没有配置驱动引擎、没有花哨的编排抽象。就是 tool calling + 循环 + 记忆。

## 结构

```
mini_agent_core/
├── agent_core/
│   ├── __init__.py      # 统一导出
│   ├── llm.py           # 用 httpx 直调 LLM API
│   ├── tools.py         # @tool 装饰器 + 自动 JSON Schema
│   ├── memory.py        # 短期滑动窗口 + 长期向量检索
│   └── agent.py         # ReAct 循环核心
├── demo.py              # 多步推理演示
├── test_all.py          # 全部测试
└── requirements.txt
```

## 安装

```bash
pip install -r requirements.txt
```

## 快速使用

```python
from agent_core import LLM, Agent
from agent_core.tools import tool

# 1. 定义工具
@tool(description="计算数学表达式")
def calculate(expression: str) -> float:
    return eval(expression)

# 2. 创建 Agent
llm = LLM(api_key="your-key")
agent = Agent(llm=llm, tools=[calculate])

# 3. 运行
result = agent.run("计算 (3+5)*2")
print(result.content)   # → 16
print(result.trace)     # → 完整推理轨迹
```

## 运行演示

```bash
export DEEPSEEK_API_KEY=your_key_here
python demo.py
```

## 测试

```bash
pytest test_all.py -v
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
                tool = ToolRegistry.get(tc.name)
                obs = tool.execute(**tc.arguments)
                messages.append({"role": "tool", ...})
            continue

        if response.content:
            if "[FINAL]" in response.content:
                return AgentResult(content=response.content)

    raise MaxIterationsError()
```

## 设计亮点

- **httpx 直调 LLM API** — 不套 OpenAI SDK，展示对 HTTP 层和 function calling 协议的底层理解
- **类型反射生成 Schema** — 从函数签名自动推断 JSON Schema，无需手写参数定义
- **异常安全执行** — 工具调用出错返回错误信息而非崩溃
- **完整 Trace** — 每次运行记录 thought → action → observation 轨迹，可审计可调试

