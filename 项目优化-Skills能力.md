# 项目优化 - Skills 能力融入方案

## 1. Skills 在项目中的定位

在 AI 健康助手 Agent 项目中，`Skills` 可以理解为“可复用的专业能力包”，介于 Prompt、Tool 和 Agent 之间。

推荐定位：

```text
Agent 负责决策和编排
Skill 负责某类稳定能力
Tool 负责具体外部调用
RAG 负责知识依据
Memory 负责用户个性化上下文
```

也就是说，Skill 不应该只是 Tool 的别名。Tool 更偏“执行一个外部动作”，例如查询天气、查询营养数据库、检索知识库；Skill 更偏“完成一段业务推理或处理流程”，例如结合用户目标、天气、运动指南生成运动计划。

## 2. 可以设计哪些 Skills

| Skill | 作用 |
|-------|------|
| `meal_analysis_skill` | 饮食描述解析、食物标准化、营养计算、饮食建议模板 |
| `exercise_plan_skill` | 运动目标解析、训练计划生成、安全校验 |
| `environment_advice_skill` | 天气/AQI 结构化解释、户外运动建议 |
| `sleep_adjustment_skill` | 睡眠状态分析、作息调整建议 |
| `health_risk_triage_skill` | 胸痛、呼吸困难、自杀意念等风险分流 |
| `rag_answer_skill` | RAG 上下文引用、忠实回答、引用格式控制 |
| `memory_resolution_skill` | 用户画像、短期记忆、长期记忆冲突消解 |
| `followup_question_skill` | 根据当前回答生成推荐追问 |

## 3. Skill 和 Tool 的区别

Tool 更像“原子能力”：

```text
fetch_weather
query_nutrition
search_rag
```

Skill 更像“业务能力”：

```text
根据天气 + 用户习惯 + 运动指南生成运动建议
```

Skill 可以内部调用 Tool，也可以调用 RAG、LLM、规则引擎和记忆系统。

例如：

```text
exercise_plan_skill
  -> 读取用户画像
  -> 检索长期运动习惯
  -> 调用 RAG 获取运动指南
  -> 使用规则生成 baseline 计划
  -> 可选调用 LLM 做计划润色
  -> 调用安全校验规则
  -> 输出结构化运动计划
```

## 4. 推荐接入方式

### 4.1 作为子 Agent 内部能力模块

可以先把 Skill 放在各个专业 Agent 内部。

例如：

```text
ExerciseAgent
  -> exercise_plan_skill
  -> safety_check_skill
  -> llm_refine_skill
```

这样子 Agent 会更薄，稳定能力可以复用，也方便单独测试。

### 4.2 建立 SkillRegistry

后续可以仿照 `ToolRegistry` 建立 `SkillRegistry`。

每个 Skill 可以声明：

```text
skill_name
description
input_schema
output_schema
required_tools
required_rag_topics
safety_level
```

主 Agent 或子 Agent 可以根据意图、任务类型和上下文选择对应 Skill。

### 4.3 在 Orchestrator 中引入 SkillPlanner

当前链路可以理解为：

```text
用户问题 -> AgentOrchestrator -> NutritionAgent / ExerciseAgent / EnvironmentAgent
```

引入 Skills 后，可以演进为：

```text
用户问题
  -> AgentOrchestrator
  -> Agent
  -> SkillPlanner
  -> 多个 Skill
  -> ToolExecutor / RAG / Memory
```

例如用户问：

```text
结合杭州天气和我周末跑步习惯，安排明天运动计划
```

可以拆成：

```text
memory_resolution_skill
environment_advice_skill
exercise_plan_skill
safety_check_skill
response_composition_skill
```

## 5. 推荐架构

```text
HealthAdvisorAgent
  -> Intent / Memory Routing
  -> SkillPlanner
  -> SkillRegistry
      -> NutritionSkill
      -> ExercisePlanSkill
      -> EnvironmentAdviceSkill
      -> RiskTriageSkill
      -> RagAnswerSkill
      -> MemoryResolutionSkill
  -> ToolExecutor
  -> ContextAssembler
  -> Response Generator
```

其中：

- `SkillPlanner` 负责根据用户意图、记忆路由、安全等级和任务依赖选择 Skill。
- `SkillRegistry` 负责统一管理 Skill 的声明和实例。
- `ToolExecutor` 仍然负责实际工具调用的白名单、超时、重试和日志。
- `ContextAssembler` 负责把 Skill 输出、RAG、记忆和工具结果分区组装进最终 Prompt。

## 6. 落地顺序

### 阶段一：先抽 Skill，不做复杂动态规划

先把现有 Nutrition / Exercise / Environment 中相对稳定的逻辑抽成普通 Python Skill 类。

建议先抽：

```text
exercise_plan_skill
environment_advice_skill
nutrition_analysis_skill
```

目标是让子 Agent 节点更薄，业务能力更容易测试。

### 阶段二：建立 SkillRegistry

定义统一接口：

```python
class BaseSkill:
    name: str
    input_schema: type
    output_schema: type

    async def run(self, input, context) -> SkillResult:
        ...
```

`SkillResult` 建议包含：

```text
skill_name
status
data
summary
confidence
warnings
citations
tool_trace
metadata
```

### 阶段三：引入 SkillPlanner

让主 Agent 或子 Agent 根据以下信息选择 Skill：

```text
intent
memory_policy
safety_flag
required_tools
rag_topics
user_profile
tool_policy
```

这个阶段再考虑动态组合多个 Skill。

## 7. 最适合优先实现的 Skills

优先建议实现：

```text
memory_resolution_skill
rag_answer_skill
```

原因是它们能直接解决项目当前最核心的问题：

1. 记忆多了之后如何做冲突消解。
2. RAG 召回内容如何组织成可靠回答。
3. 短期记忆、长期记忆、画像、RAG、工具结果如何融合。
4. 如何控制引用、忠实度和上下文边界。

之后再抽：

```text
exercise_plan_skill
environment_advice_skill
nutrition_analysis_skill
followup_question_skill
```

## 8. 融入后的收益

引入 Skills 后，项目会从：

```text
多 Agent + 工具 + RAG
```

演进为：

```text
多 Agent 编排 + 可复用 Skills + 统一工具执行 + 统一上下文治理
```

主要收益：

1. 子 Agent 更薄，职责更清晰。
2. 稳定业务能力可以复用和单测。
3. Skill 可以成为评估和版本迭代的最小单元。
4. 工具调用仍然受 ToolExecutor 统一治理。
5. RAG、Memory、Tool、LLM 的边界更清楚。
6. 后续新增 SleepAgent、心理压力评估、健康周报等能力时，可以复用已有 Skill。
