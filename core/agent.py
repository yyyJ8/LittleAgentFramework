"""
Agent 基类 — ReAct 循环核心。

展示对 Agent 最底层循环逻辑的理解：
thought → action → observation → thought ... → final answer
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from .llm import LLM, LLMResponse
from .tools import Tool, ToolRegistry
from .memory import SlidingWindowMemory


# ─── 结果类型 ───────────────────────────────────────────────


@dataclass
class AgentResult:
    """Agent 执行结果"""
    content: str
    trace: list[dict] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    iterations: int = 0


# ─── Agent 配置 ──────────────────────────────────────────────


@dataclass
class AgentConfig:
    system_prompt: str = ""
    max_iterations: int = 10
    tool_descriptions: str = ""


# ─── ReAct 提示词模板 ─────────────────────────────────────


DEFAULT_SYSTEM_PROMPT = """你是一个擅长多步推理的 AI 助手。你有以下工具可用：

{tool_descriptions}

请按以下格式思考和回答：

Thought: 分析当前情况，决定下一步做什么
Action: 工具名称
Action Input: {{"参数名": "参数值"}}

...（可多次重复 Thought → Action → Observation 步骤）

当你得到足够信息后：

Thought: 我已经得到足够信息
Final Answer: 最终回答

请用中文思考并回答问题。"""


# ─── Agent 类 ───────────────────────────────────────────────


class Agent:
    """ReAct Agent — 思考→行动→观察→思考...→最终答案"""

    def __init__(
        self,
        llm: LLM,
        tools: list[Tool] | None = None,
        system_prompt: str | None = None,
        max_iterations: int = 10,
        memory: SlidingWindowMemory | None = None,
        hooks: dict[str, Callable] | None = None,
    ):
        self.llm = llm
        self.max_iterations = max_iterations
        self.memory = memory or SlidingWindowMemory()

        # 注册工具
        self.tools = tools or []
        for t in self.tools:
            if isinstance(t, Tool):
                ToolRegistry.register(t.func, name=t.name, description=t.description)
            elif callable(t):
                # 兼容 @tool 装饰过的函数
                name = getattr(t, '_tool_name', None) or t.__name__
                ToolRegistry.register(t, name=name)

        # 系统提示词
        tool_descs = self._format_tool_descriptions()
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT.format(
            tool_descriptions=tool_descs
        )

        # 钩子
        self.hooks = hooks or {}

    def run(self, user_input: str) -> AgentResult:
        """ReAct 循环主入口"""
        from .tools import ToolRegistry

        trace: list[dict] = []
        total_usage: dict[str, int] = {}

        # 构建初始消息
        messages = [{"role": "system", "content": self.system_prompt}]

        # 加载短期记忆
        messages.extend(self.memory.get_context())

        # 加入用户输入
        messages.append({"role": "user", "content": user_input})

        # ── ReAct 循环 ────────────────────────────────
        for iteration in range(self.max_iterations):
            response = self.llm.chat(messages, tools=ToolRegistry.schemas())

            self._accumulate_usage(total_usage, response.usage)

            # 情况 1：LLM 要求调用工具
            if response.tool_calls:
                for tc in response.tool_calls:
                    tool = ToolRegistry.get(tc.name)
                    if not tool:
                        obs = f"错误: 未找到工具 '{tc.name}'"
                    else:
                        obs = tool.execute(**tc.arguments)

                    trace.append({
                        "iteration": iteration,
                        "thought": response.content or "",
                        "tool": tc.name,
                        "arguments": tc.arguments,
                        "observation": obs,
                    })

                    self._call_hook("on_tool_call", trace[-1])

                    messages.append({
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments),
                                },
                            }
                        ],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": obs,
                    })

            # 情况 2：文本回复 → Final Answer
            if response.content and not response.tool_calls:
                # 检查 Final Answer 标记
                content = response.content
                if "[FINAL]" in content or iteration == self.max_iterations - 1:
                    clean_content = content.replace("[FINAL]", "").replace("Final Answer:", "").strip()
                    trace.append({
                        "iteration": iteration,
                        "thought": content,
                        "final_answer": clean_content,
                    })
                    self._call_hook("on_final", trace[-1])
                    return AgentResult(
                        content=clean_content,
                        trace=trace,
                        usage=total_usage,
                        iterations=iteration + 1,
                    )

                # 没有 Final Answer 标记但有内容→可能是 Thought，继续循环
                # 有 tool_calls 时 content 也会被带上的，如 "Thought: 我先计算...\nAction: calculate"
                if iteration < self.max_iterations - 1:
                    messages.append({"role": "assistant", "content": content})
                    continue

            # 情况 3：response 既无 content 也无 tool_calls（极少数情况）
            if not response.content and not response.tool_calls:
                messages.append({
                    "role": "assistant",
                    "content": "（空响应，请继续）",
                })
                continue

        # 超时返回
        return AgentResult(
            content="（已达最大迭代次数，未能得出最终答案）",
            trace=trace,
            usage=total_usage,
            iterations=self.max_iterations,
        )

    # ── 内部方法 ────────────────────────────────────────

    def _format_tool_descriptions(self) -> str:
        """生成工具描述文本（嵌入 system prompt）"""
        if not self.tools:
            return "（无可用工具）"
        from .tools import Tool
        lines = []
        for t in self.tools:
            if isinstance(t, Tool):
                params = ", ".join(t.parameters.get("properties", {}).keys())
                lines.append(f"- {t.name}({params}): {t.description}")
            else:
                # 兼容原始函数（有 name 属性）
                lines.append(f"- {getattr(t, '__name__', str(t))}(...): 可用工具")
        return "\n".join(lines)

    def _accumulate_usage(self, total: dict, current: dict) -> None:
        for key, val in current.items():
            total[key] = total.get(key, 0) + val

    def _call_hook(self, name: str, data: dict) -> None:
        hook = self.hooks.get(name)
        if hook:
            hook(data)
