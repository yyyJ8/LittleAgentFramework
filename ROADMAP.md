# 迭代方向

三个方向由浅入深，每个都能独立展示。

---

## 1. 流式输出（streaming）

**现在**：`llm.chat()` 等完整响应，Agent 思考过程一次性吐出。

**目标**：每轮 Thought 逐字输出，打字机效果。

**改哪里**：

```
core/llm.py:
  chat() → chat_stream()，httpx 加 stream=True，逐 chunk yield

core/agent.py:
  run() → run_stream()，接收流式 response，实时 print 或 yield trace 事件

demo/reasoning_stream.py:
  新增，展示流式推理效果
```

**效果**：

```
🤖 我来计算光到地球的时间...
   💭 已知距离 d = 1.496e11, 光速 c = 3e8
   💭 公式 t = d/c
   🔧 调用 calculate("1.496e11 / 3e8")
   📤 498.67 秒
   💭 换算：498.67 / 60 = 8.31 分钟
✅ 约 8 分 19 秒
```

每个 💭 逐字打出来，不是一次性吐。

---

## 2. 多 Agent 辩论

**现在**：单 Agent 自己思考自己回答。

**目标**：多个 Agent 互相对话、质疑、收敛到更可靠的答案。

**改哪里**：

```
core/debate.py:        ← 新增，辩论编排层
demo/debate_demo.py:   ← 新增，辩论演示
```

**架构**：

```
User 问题
   │
   ▼
┌─────────────────────────┐
│  SharedContext           │  ← 就是现在的 SlidingWindowMemory
│  (所有 Agent 共享)       │
└─────────────────────────┘
   │         │
   ▼         ▼
Agent A    Agent B     ← 同一问题，不同视角（如 A 偏激进、B 偏保守）
   │         │
   └────┬────┘
        ▼
    Judge Agent        ← 裁判，读所有人的论据，给出最终结论
```

**Agent 角色分工**：

| 角色 | 职责 |
|------|------|
| Solver | 回答问题 |
| Critic | 挑毛病、找漏洞 |
| Judge | 综合双方观点，给出最终答案 |

**核心逻辑**（约 50 行）：

```python
class Debate:
    def __init__(self, agents: list[Agent], judge: Agent, max_rounds: int = 3):
        self.agents = agents
        self.judge = judge
        self.max_rounds = max_rounds

    def run(self, question: str) -> list[dict]:
        context = [{"role": "user", "content": question}]

        for round_num in range(self.max_rounds):
            for agent in self.agents:
                response = agent.run(context)  # Agent 看到完整上下文
                context.append({"role": "assistant", "name": agent.name,
                                "content": response.content})

        # 裁判给出最终结论
        verdict = self.judge.run(context)
        return {"debate": context, "verdict": verdict}
```

**为什么有效**：单 Agent 容易自欺，多个视角互相验证错误率显著下降。

---

## 3. Trace 可视化

**现在**：推理轨迹打印到终端，纯文本。

**目标**：生成可交互的 HTML 页面，展示 Agent 思考过程。

**改哪里**：

```
core/trace.py:         ← 新增，Trace → HTML 渲染器
demo/trace.html:       ← 新增，前端模板
demo/export_demo.py:   ← 新增，运行推理并导出 HTML
```

**要做的事**：

```
Agent.run() 返回 trace  ──→  TraceRenderer(trace).to_html()  ──→  浏览器打开
```

**页面效果**：

```
┌─ 🔍 光从太阳到地球需要多长时间？ ─────────────┐
│                                                │
│  ┌─ 第 1 轮 ──────────────────────────────┐   │
│  │  💭 分析公式 t = d / c                  │   │
│  │  🔧 calculate("1.496e11 / 3e8")         │   │
│  │  📤 498.67 秒                           │   │
│  │       ↓                                 │   │
│  │  💭 换算成分钟                          │   │
│  │  🔧 calculate("498.67 / 60")            │   │
│  │  📤 8.31 分钟                           │   │
│  └──────────────────────────────────────────┘   │
│                                                │
│  ✅ 约 8 分 19 秒                              │
│                                                │
│  ═══════════════════════════════════════════   │
│  📊 Token: 9,461  │  ⏱ 2.3s  │  🔄 2 轮     │
└────────────────────────────────────────────────┘
```

展开/折叠每轮、高亮工具调用、显示耗时和 token 用量。

---

## 建议顺序

| 顺序 | 方向 | 工时 | 理由 |
|:----:|------|:----:|------|
| 1 | 流式输出 | 1h | 改动最小，立竿见影 |
| 2 | 多 Agent 辩论 | 3h | 结构清晰，面试展示力强 |
| 3 | Trace 可视化 | 3h | 锦上添花，浏览器打开即惊艳 |

**这三个做完，项目就从一个"能跑的 demo"变成"能展示完整 Agent 理解力的作品"。**
