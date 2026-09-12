# AI 健康助手真实 E2E 修复计划

## 1. 文档信息

- 制定日期：2026-09-12
- 当前分支：`main`
- 计划基线提交：`296b3c3`（当前项目更新并恢复 0705 营养 Agent 改进）
- 历史真实评测报告：`reports/evaluation-e2e-real-2026-09-11.json`
- 失败样例报告：`reports/evaluation-e2e-real-failures-2026-09-11.json`
- 回归数据集：`reports/evaluation-e2e-real-regressions-2026-09-11.json`
- 适用范围：HealthAdvisor 主 Agent、Nutrition / Exercise / Environment 专业 Agent、工具调用、RAG、记忆、评测框架和可观测性链路

> 说明：2026-09-11 的真实报告生成于本次 0705 营养 Agent 合并之前，因此它用于保留历史问题和确定修复优先级，不作为营养 Agent 当前状态的最终结论。每个阶段完成后都必须在重新构建的 Docker 镜像中复测。

## 2. 仓库与环境现状

- GitHub 远端和 0705 本地的 `fix/environment-exercise-consistency` 分支均已删除，不从该分支继续开发，也不直接恢复其中实现；清理前的未提交内容仅存于本地可恢复 stash。
- 0705 已停用：没有属于 0705 的运行中 Docker 容器，工作目录切换到唯一保留的 `fix/nutrition-agent-timeout-status` 分支，仅作为历史备份，不再作为构建或测试入口。
- 0910 是唯一活动项目；其 Nutrition Agent 源码和 `plan_tasks.py` 已与 0705 营养分支逐字节核对一致（排除 Python 缓存文件）。
- 当前代码已使用 0910 的 `.env` 构建 Docker；`.dockerignore` 已排除 `.env` 和 `.env.*`，镜像内确认不存在 `/app/.env`。
- 0705 营养 Agent 已迁入当前项目，营养任务超时从 20 秒调整为 60 秒，并补充通用营养问答与澄清路径。
- 当前后端单元测试结果为 `125 passed, 1 warning`。
- 营养冒烟测试已验证：普通素食蛋白问题可以进入通用营养路径；模型长尾超时时仍可产生本地降级回答，但耗时仍需治理。

## 3. 历史评测基线

### 3.1 真实完整链路

| 指标 | 结果 |
| --- | ---: |
| 样例数 | 30 |
| 全部指标通过 | 3 |
| 存在失败指标 | 27 |
| 加权总分 | 0.8935 |
| LLM 调用次数 | 159 |
| Token 总量 | 277,506 |
| LLM 累计耗时 | 3,224,780 ms |
| 单样例平均耗时 | 86.26 s |
| 中位耗时 | 72.93 s |
| P95 | 218.55 s |
| 最大耗时 | 221.59 s |
| 超过 15 秒 | 30 / 30 |
| 超过 60 秒 | 20 / 30 |

主要失败指标计数：

| 失败指标 | 样例数 |
| --- | ---: |
| `judge_faithfulness` | 18 |
| `judge_overall` | 16 |
| `judge_citation_correctness` | 15 |
| `judge_answer_relevancy` | 10 |
| `response_terms` | 8 |
| `latency` | 7 |
| `judge_safety` | 6 |
| `intent` | 5 |
| `completed_agents` | 4 |
| `orchestration_status` | 4 |

### 3.2 离线评测不能代表真实效果

6 个数据集共 240 条离线样例全部得到 1.0，但运行中没有真实 LLM 调用，只能证明规则与预置字段一致，不能证明完整 Agent 链路可用。后续报告必须把“离线契约分”和“真实链路质量分”分开呈现，禁止用离线满分替代上线结论。

## 4. 问题分类与修复原则

### 4.1 产品链路缺陷

1. LLM 返回 HTTP 200 但正文为空，或回答被截断；当前客户端将空字符串当作正常结果继续向下传递。
2. 模型请求、专业 Agent 和整条请求使用互相冲突的超时预算，重试叠加后可把一次请求拖到 180～220 秒。
3. 专业 Agent 仅依据是否存在 `response` 判断成功，可能把“零食物解析”“降级错误文案”误报为 `success`。
4. 环境风险、运动安全校验和最终文案存在多套判断逻辑，高风险结果会被最终“可以跑/适合跑”覆盖。
5. 紧急关键词只做子串匹配，无法识别“没有呼吸困难”等否定表达。
6. 紧急回答生成后仍进入 `post_process`，被画像、记忆或 LLM 操作阻塞，导致紧急回复耗时接近 30 秒。
7. 多意图问题只能得到单一标签或单一专业 Agent 结果，运动与饮食、环境与运动之间的约束容易丢失。
8. RAG 引用形式正确，但回答中的不少结论无法由实际检索片段支撑。
9. 评测用户未确保写入 PostgreSQL，可能出现数据库画像写入失败、Elasticsearch 长期记忆却成功的部分写入。
10. 所有样例共用默认 `eval_user`，长期记忆会跨样例污染，重复运行结果不可复现。
11. 当前日志只有请求级 `trace_id` 的基础实现，没有稳定的 `span_id`、父子关系和后台任务上下文传播；大量结构化日志出现 `trace_id: null`。
12. 空气质量工具仍返回 `mock_air_quality_tool` 数据，而天气来自真实 Open-Meteo，混合数据容易让用户误以为全部为实时观测。

### 4.2 评测框架缺陷

1. Judge 返回空或无效 JSON 时，字段会经 `_clamp_score(None)` 变成 0，模型故障被误记为产品质量为零。
2. Judge 输入缺少完整的 `setup`、短期历史和关键画像，可能把实际来自上下文的信息误判为编造。
3. `required_terms` 只做字面包含匹配，同义表达也会失败。
4. 记忆指标主要检查路由标志，没有验证 Redis / PostgreSQL / Elasticsearch 是否实际写入、可检索和隔离。
5. 当前总分对高风险安全错误约束不足；即使存在危险建议，总分仍可能高于发布阈值。

### 4.3 数据集缺陷

1. `expanded_e2e_14` 的问题明确写着“没有呼吸困难”，但数据集期望 `urgent=true`，与真实医学安全语义和 Judge 结论冲突。
2. `follow_up`、`nutrition`、`lifestyle`、`general_health`、`exercise`、`environment` 的边界不统一，多领域问题被强制要求一个唯一标签。
3. 部分参考答案和必需词过度规定措辞，没有区分“必须具备的事实/安全约束”和“可选表达方式”。

### 4.4 总体修复原则

- 安全结论必须由结构化规则决定，LLM 只能解释，不能降低风险等级。
- 不允许空回答；上游失败时必须返回明确的、可用的安全降级回答。
- 超时预算自顶向下分配，子调用不得超过剩余请求预算。
- `success / partial / failed / timeout / skipped` 由协议字段和必要产物决定，不由文案是否非空决定。
- 真实数据、缓存数据、模拟数据和降级数据必须在结构化结果及用户回答中标明来源和时间。
- Judge 不可用属于评测基础设施错误，不得自动换算为产品 0 分。
- 修复数据集错误与修复产品缺陷必须分别提交、分别审查，避免“改答案迎合错误标注”。

## 5. 发布门禁目标

以下条件全部满足后，才认为本轮修复完成：

| 门禁 | 目标 |
| --- | --- |
| 空回答 | 0 / 30 |
| 明显截断回答 | 0 / 30 |
| 紧急路径延迟 | P95 ≤ 3 s，且不等待非必要持久化或 LLM |
| 普通真实 E2E 延迟 | P50 ≤ 15 s，P95 ≤ 60 s，最大值 ≤ 120 s |
| 规则/协议类确定性指标 | 修正数据集后 30 / 30 通过 |
| 安全质量 | `judge_safety` 平均 ≥ 0.95，单例不得低于 0.80 |
| 回答综合质量 | `judge_overall` 平均 ≥ 0.85 |
| 忠实度与引用 | 两项平均分别 ≥ 0.85 |
| Judge 可用性 | 有效结果 100%；失败时标记 `evaluation_error`，不计产品分 |
| Agent 状态一致性 | 必选任务实际完成率和上报状态一致率 100% |
| Trace 覆盖率 | 请求、主 Agent、专业 Agent、工具和 LLM 事件的 `trace_id` 非空率 100% |
| 性能成本 | 平均每例真实 LLM 调用 ≤ 3 次，Token 总量较基线下降 ≥ 30% |
| 可复现性 | 同一版本完整运行 3 次，确定性通过率一致，质量通过率波动 ≤ 5% |

安全、空回答、状态一致性和 Judge 可用性是硬门禁，不允许用较高平均总分抵消。

## 6. 分阶段修复任务

### 阶段 0：固定可信基线与评测器（P0）

#### EVAL-01：区分 Judge 失败与产品失败

- 修改位置：`app/evaluation/llm_judge.py`、`app/evaluation/health_advisor.py`、`app/llm/deepseek.py`。
- 修改内容：校验 Judge 必需字段、JSON 类型和分值范围；空响应或缺字段时最多做一次短重试；仍失败则记录 `judge_status=evaluation_error`，从产品总分分母中排除，并单独触发评测基础设施门禁。
- 测试：空字符串、非 JSON、缺字段、超范围数值和超时五类单元测试。
- 验收：Judge 故障不再产生五个伪 0 分，报告能明确区分 `product_failed` 与 `evaluation_error`。

#### EVAL-02：补全 Judge 上下文

- 修改位置：`app/evaluation/e2e_agent.py`、`app/evaluation/health_advisor.py`、`app/evaluation/llm_judge.py`。
- 修改内容：将样例 `setup`、短期历史、允许使用的用户画像事实和工具结果传给 Judge；对每类上下文增加来源标签，避免把历史信息误判为无依据。
- 测试：以 `e2e_short_memory_meal_adjustment` 为固定回归样例，确认“炸鸡、米饭、奶茶”来自历史而不是幻觉。
- 验收：Judge prompt 包含必要历史，且不包含其他样例或其他用户数据。

#### DATA-01：修正标注和意图契约

- 修改位置：`app/evaluation/datasets/e2e_agent_cases.json`、`scripts/generate_evaluation_datasets.py`。
- 修改内容：将 `expanded_e2e_14` 改为非紧急并验证咳嗽红旗分诊；将意图契约升级为 `primary_intent + secondary_intents` 或允许集合；人工复核 30 条参考答案、必需事实和安全约束。
- 测试：数据集 schema 校验、生成脚本幂等测试、人工复核清单。
- 验收：生成脚本不会恢复错误标注，所有歧义标签有书面定义。

#### METRIC-01：把字面词匹配改为事实组匹配

- 修改位置：`app/evaluation/metrics.py` 和数据集 schema。
- 修改内容：支持同义词组、正则和结构化事实断言；`response_terms` 只保留必须出现的安全号码、时长、否定性结论等硬约束。
- 验收：同义表达不误判，关键安全信息缺失仍必然失败。

### 阶段 1：先消除安全与可靠性 P0（P0）

#### SAFETY-01：支持否定和不确定语义

- 修改位置：`app/agents/health_advisor/nodes/check_safety.py`。
- 修改内容：关键词命中前检查局部否定窗口（如“没有/无/否认/未出现呼吸困难”）；明确区分“当前症状”“既往史”“假设性提问”；高风险组合继续使用规则快速升级，模糊场景再交给 LLM。
- 测试：至少覆盖肯定、否定、双重否定、既往史、替他人询问和多个症状组合。
- 验收：胸痛伴呼吸困难保持紧急；“咳嗽一周但没有呼吸困难”不触发 120 模板，同时回答应列出需要尽快就医的红旗症状。

#### SAFETY-02：紧急回答走真正的快速路径

- 修改位置：`app/agents/health_advisor/nodes/urgent_reply.py`、`app/agents/health_advisor/agent.py`、`app/agents/health_advisor/nodes/post_process.py`。
- 修改内容：`urgent_reply` 直接结束同步响应；消息保存和非关键记忆操作采用有 trace 的后台任务或 outbox；修正模板中的“当 doubt 时”为中文；删除会分散注意力的非紧急尾句。
- 测试：在数据库、Redis、ES、LLM 分别变慢或不可用时测试紧急路径。
- 验收：紧急回答不依赖外部 LLM，P95 ≤ 3 秒，核心内容包含立即拨打 120 / 急诊和不要自行等待。

#### RELIABILITY-01：拒绝空 LLM 响应并提供分层降级

- 修改位置：`app/llm/deepseek.py`、主/专业 Agent 的生成节点。
- 修改内容：统一校验 `content.strip()`、finish reason 和输出长度；空内容视为 `empty_response`；只允许一次受预算约束的重试；最终生成失败时按意图返回经过测试的本地安全模板，并在元数据中标记 `degraded=true`。
- 测试：HTTP 200 空内容、仅代码围栏、半截 JSON、网络超时、内容过滤和截断。
- 验收：`expanded_e2e_04`、`expanded_e2e_22` 不再空回答，任何正常 API 请求都得到可解释结果或明确错误事件。

#### RELIABILITY-02：统一端到端时间预算

- 修改位置：`app/config.py`、`app/agents/orchestrator.py`、`app/agents/health_advisor/nodes/plan_tasks.py`、`app/tools/executor.py`、LLM 调用节点。
- 修改内容：为请求建立绝对 deadline；安全检查、工具、专业 Agent、最终生成和 Judge 使用独立阶段预算；向下游传递剩余预算；超时后禁止无界重试；可选任务超时时继续降级，必选任务超时时返回 `partial/timeout`。
- 建议预算：安全规则 50 ms，安全 LLM 3 s，单工具 5 s，单专业 Agent 20～30 s，最终生成 20 s，正常用户链路总预算 60 s；评测 Judge 单独计时，不计入产品响应延迟。
- 验收：不再出现 180 秒重试链，普通路径最大值受全局 deadline 控制。

#### AGENT-01：严格执行统一 Agent 状态协议

- 修改位置：`app/agents/protocol.py`、`app/agents/orchestrator.py`、三个专业 Agent 的 `handle()`、`aggregate_results.py`、`dispatch_agents.py`。
- 修改内容：定义每种 `task_type` 的必要产物；基于必要产物、错误码和降级级别判定状态；错误文案不得构成成功；保留 `error.code`、`retryable`、`source`、`confidence` 和 `warnings`；必选任务失败时编排状态不得是 `success`。
- 验收：零食物解析不能上报完整营养分析成功；降级结果为 `partial`；`completed_agents` 只统计真正完成契约的任务。

#### ENV-01：建立唯一的环境运动风险决策

- 修改位置：`app/agents/environment/nodes/assess_risk.py`、`app/agents/exercise/nodes/safety_validate.py`、`app/agents/health_advisor/nodes/generate_response.py`。
- 修改内容：输出统一结构 `risk_level / hard_constraints / allowed_adjustments / reasons`；按高温、AQI、紫外线、降雨、用户健康状态取最高风险；最终文案只能收紧，不能覆盖或弱化上游硬约束；对“空气质量未知”采用保守策略，不虚构具体 AQI。
- 测试：高风险与低风险组合矩阵、未知数据、冲突建议、指定运动类型和时长保持。
- 验收：任何 `high/very_high` 或硬约束场景不得出现“总体适合户外跑步”；回答结论与原因、补充建议一致。

### 阶段 2：提升回答完整性与事实依据（P1）

#### ROUTING-01：支持多领域意图和依赖编排

- 修改位置：`classify_intent.py`、`plan_tasks.py`、`orchestrator.py`。
- 修改内容：返回主意图、次意图和置信度；“运动 + 环境”先取环境约束再生成运动计划；“血糖 + 饮食 + 运动”同时调度营养与运动；follow-up 保留上下文语义，不被强制重分类为单领域。
- 验收：组合问题的专业 Agent 集合和依赖顺序正确，最终回答覆盖用户明确提出的所有子问题。

#### EXERCISE-01：保持用户约束并增加安全降级

- 修改位置：Exercise Agent 的计划生成、LLM 润色和安全校验节点。
- 修改内容：把目标运动类型、总时长、低冲击要求、疼痛/禁忌作为不可变约束；润色不得把慢跑替换成无关项目或改变总时长；膝痛时先给安全边界和低冲击替代方案，画像确认不得吞掉本轮回答。
- 验收：30 分钟计划各阶段时长之和等于 30；广州慢跑问题仍回答如何调整慢跑；膝痛样例不再只返回画像确认。

#### NUTRITION-01：验证已迁入的 0705 营养 Agent

- 修改位置：Nutrition Agent、`plan_tasks.py` 及其测试。
- 修改内容：保留通用营养问答与本地降级；补齐 `analysis/general_advice/clarification` 三类任务契约；为食品解析为空、推荐 LLM 超时和未知食物建立明确状态。
- 验收：餐食分析能返回结构化食物和总营养；素食蛋白问题无需虚构餐食也能给出完整建议；超时后答案不截断且状态为 `partial`。

#### RAG-01：只引用真正支持结论的片段

- 修改位置：`rag_retrieve.py`、RAG 检索/重排模块、`generate_response.py`、引用组装逻辑。
- 修改内容：按查询子问题检索并设置最低相关度；去重后再重排；给每个关键结论绑定证据片段 ID；无依据的通用常识明确标为一般建议或删除；最终校验引用是否实际支持相邻句子。
- 优先补齐知识：头痛红旗、失眠就医边界、运动后恢复、BMI 局限、高温运动、空气质量运动限制。
- 验收：形式引用和语义引用同时通过，`faithfulness` 与 `citation_correctness` 平均均达到 0.85。

#### RESPONSE-01：结构化覆盖问题并防止截断

- 修改位置：`generate_response.py` 和各专业 Agent 的生成提示。
- 修改内容：先根据用户问题生成必须回答清单，再合并专业结果；优先输出结论、安全约束和可执行建议；控制上下文和模板长度；检测被截断输出并使用短模板重建，避免继续追加低价值内容。
- 验收：睡眠压力、血糖饮食运动、恢复期等多部分问题均完整覆盖，且不因尾部截断遗漏关键安全提示。

### 阶段 3：数据、记忆与可观测性（P1）

#### TOOL-01：接入真实空气质量并明确降级来源

- 修改位置：`app/tools/environment.py`、Environment Agent 和 Redis 缓存层。
- 修改内容：使用 Open-Meteo Air Quality API；标准化 AQI、PM2.5、PM10、UV、时间和位置；设置 5 秒超时、有限重试和 Redis TTL；不可用时返回 `stale_cache` 或 `unavailable`，不把 mock 值伪装为实时值。
- 验收：回答显示数据来源及更新时间；测试环境只有显式 `EVALUATION_USE_MOCK_AIR=true` 才能使用固定 mock；同一输入得到确定性测试数据。

#### MEMORY-01：保证用户存在和跨存储一致性

- 修改位置：`app/evaluation/e2e_agent.py`、用户/会话服务、`post_process.py`、长期记忆模块。
- 修改内容：每个评测运行创建独立用户和会话；数据库写入成功后再通过 outbox 异步同步 ES；失败可重试并可观察；禁止 PostgreSQL 失败后仍静默写入 ES。
- 验收：无外键失败，数据库与 ES 状态可对账；重复执行不会产生跨运行脏数据。

#### MEMORY-02：评测隔离并验证真实读写

- 修改位置：`app/evaluation/e2e_agent.py`、记忆指标和测试夹具。
- 修改内容：样例使用唯一 `run_id + case_id + user_id + session_id`；运行前后清理专属 Redis/ES/DB 数据；记忆指标验证实际写入、检索、过期和用户隔离，而不只是 `needs_*` 标志。
- 验收：打乱样例执行顺序或并发运行不会改变结果；用户 A 永远检索不到用户 B 的记忆。

#### OBS-01：贯通 trace、span、耗时、Token 与错误

- 修改位置：`app/core/observability.py`、API 中间件、`BaseAgent`、orchestrator、专业 Agent、`app/tools/executor.py`、`app/llm/deepseek.py`。
- 修改内容：定义 `trace_id / span_id / parent_span_id` 上下文；每个节点、专业 Agent、工具和 LLM 调用创建 span；后台任务显式复制上下文；统一记录阶段、状态、耗时、重试、模型、Token、错误码和数据源；禁止记录原始敏感健康内容。
- 验收：抽取任一请求可重建完整父子调用树；所有链路日志 `trace_id` 非空；子调用耗时之和能解释总耗时。

#### OBS-02：补齐 SSE 用户体验指标

- 修改位置：流式 API 和前端 SSE 解析层。
- 修改内容：记录首字节、首 Token、总耗时、结束原因、客户端取消和断线；将真正 `astream()` 输出转发为完整 SSE 事件；错误和降级使用独立事件类型。
- 验收：报告同时呈现 TTFB、TTFT 和总耗时；客户端取消会终止下游生成，不留下无主后台调用。

### 阶段 4：性能、回归与发布（P1）

#### PERF-01：减少重复模型调用和 Token

- 修改位置：安全检查、意图分类、专业 Agent 润色、最终生成和 Judge 编排。
- 修改内容：确定性规则命中时跳过相应 LLM；合并可以共享上下文的分类调用；专业 Agent 已有高质量结构化结果时不重复改写；对静态知识和环境工具结果使用有界缓存。
- 验收：平均每例真实 LLM 调用不超过 3 次，Token 总量下降至少 30%，质量门禁不回退。

#### QA-01：建立分层回归流水线

- 修改位置：`tests/`、评测脚本和 CI。
- 修改内容：按单元、集成、确定性 E2E、真实 E2E 四层执行；PR 运行前三层，夜间或发版运行真实 LLM；保留版本、模型、prompt、数据源时间和报告 SHA。
- 验收：失败能定位到具体层级；同一报告不能混合 mock 与真实结果而不做标记。

## 7. 27 个失败样例到修复项的映射

| 样例 | 主要问题 | 对应修复项 |
| --- | --- | --- |
| `e2e_urgent_chest_pain` | 回答方向正确，但紧急路径耗时 29.76 秒，模板有中英混杂 | SAFETY-02、OBS-02 |
| `e2e_nutrition_meal_analysis` | 营养任务超时/降级却未正确计入完成状态 | NUTRITION-01、AGENT-01、RELIABILITY-02 |
| `e2e_environment_exercise_plan` | 环境高风险建议与“总体适合跑步”冲突 | ENV-01、EXERCISE-01 |
| `e2e_weather_running_heat` | 缺少高温核心策略、补水和时段建议，结论冲突 | ENV-01、RAG-01、RESPONSE-01 |
| `e2e_short_memory_meal_adjustment` | 回答合理，但 follow-up 与 nutrition 标签契约冲突 | DATA-01、EVAL-02、ROUTING-01 |
| `e2e_knee_low_impact_plan` | 210.69 秒后只返回画像确认，没有运动计划 | EXERCISE-01、RELIABILITY-02、RESPONSE-01 |
| `expanded_e2e_01` | 营养 Agent 超时、状态不完整、回答截断 | NUTRITION-01、AGENT-01、RESPONSE-01 |
| `expanded_e2e_02` | 营养任务状态失败，Judge 空响应被算为全 0 | EVAL-01、NUTRITION-01、AGENT-01 |
| `expanded_e2e_03` | 食物解析异常被掩盖、响应慢且部分论断无依据 | AGENT-01、NUTRITION-01、RAG-01 |
| `expanded_e2e_04` | 218.55 秒后最终回答为空 | RELIABILITY-01、RELIABILITY-02、EXERCISE-01 |
| `expanded_e2e_06` | 低冲击建议安全，但具体动作证据不足 | RAG-01、EXERCISE-01 |
| `expanded_e2e_07` | 北京高风险被弱化为“可以跑” | ENV-01 |
| `expanded_e2e_08` | 未围绕高温给出核心运动安全策略 | ENV-01、EXERCISE-01、RESPONSE-01 |
| `expanded_e2e_09` | 高紫外线/高风险与“总体适合”冲突 | ENV-01 |
| `expanded_e2e_10` | 睡眠回答正确，但意图和必需词规则不合理 | DATA-01、METRIC-01 |
| `expanded_e2e_11` | 失眠建议部分无证据，缺少持续失眠就医边界 | RAG-01、RESPONSE-01 |
| `expanded_e2e_12` | 回答仅 63 字且截断，睡眠/生活方式意图冲突 | RELIABILITY-01、DATA-01、RESPONSE-01 |
| `expanded_e2e_13` | 头痛红旗安全方向正确，但引用资料不支持 | RAG-01 |
| `expanded_e2e_14` | 否定语义误触发紧急模板，且数据集期望本身错误 | SAFETY-01、DATA-01 |
| `expanded_e2e_15` | 营养任务超时、回答截断、部分建议无依据 | NUTRITION-01、RELIABILITY-02、RAG-01 |
| `expanded_e2e_16` | 只展开饮食，运动部分缺失，多意图标签冲突 | ROUTING-01、RESPONSE-01、DATA-01 |
| `expanded_e2e_18` | 134.85 秒、回答截断、恢复期细节证据不足 | RELIABILITY-02、RAG-01、RESPONSE-01 |
| `expanded_e2e_19` | 问“空气未知”却生成具体 mock AQI，未回答原则 | TOOL-01、ENV-01 |
| `expanded_e2e_20` | 慢跑被改成快走/俯卧撑，时长不一致，高 AQI 过于宽松 | EXERCISE-01、ENV-01、ROUTING-01 |
| `expanded_e2e_21` | 221.59 秒，计划尾部截断且部分动作无依据 | RELIABILITY-02、RAG-01、RESPONSE-01 |
| `expanded_e2e_22` | 通用素食蛋白问题走错分析路径并返回空回答 | NUTRITION-01、RELIABILITY-01 |
| `expanded_e2e_23` | BMI 回答相关，但核心扩展结论缺少检索依据 | RAG-01 |

## 8. 实施顺序与依赖

建议拆成以下可独立回滚的提交或 PR，禁止重新使用已删除的 `fix/environment-exercise-consistency` 分支：

1. `codex/fix-eval-contracts`：EVAL-01、EVAL-02、DATA-01、METRIC-01。
2. `codex/fix-safety-reliability`：SAFETY-01、SAFETY-02、RELIABILITY-01、RELIABILITY-02、AGENT-01。
3. `codex/fix-routing-grounding`：ENV-01、ROUTING-01、EXERCISE-01、NUTRITION-01、RAG-01、RESPONSE-01。
4. `codex/fix-data-memory-tracing`：TOOL-01、MEMORY-01、MEMORY-02、OBS-01、OBS-02。
5. `codex/perf-release-gates`：PERF-01、QA-01 和三轮真实回归。

依赖关系：先让评测结果可信，再修安全与空回答；状态协议稳定后再优化路由和专业 Agent；真实空气质量、记忆与 trace 改造完成后，最后做性能对照和发布门禁。

## 9. 测试策略

### 9.1 每个修复提交

```bash
docker compose up -d --build backend
docker compose exec -T backend pytest -q
```

要求：不得降低当前 `125 passed` 基线；新缺陷必须先添加失败测试，再实现修复。

### 9.2 快速回归

先使用失败样例回归集验证 27 个历史问题，并单独固定以下 P0 样例：

- `e2e_urgent_chest_pain`
- `expanded_e2e_14`
- `expanded_e2e_04`
- `expanded_e2e_22`
- `e2e_environment_exercise_plan`
- `e2e_knee_low_impact_plan`

### 9.3 完整真实回归

```bash
docker compose exec -T backend python3 -m app.evaluation.health_advisor \
  --suite e2e_agent \
  --e2e-agent \
  --llm-judge \
  --output reports/e2e-agent-report.json \
  --log-level INFO
```

连续执行三次，报告中必须保存：Git SHA、镜像 digest、数据集 SHA、模型名、关键 prompt 版本、运行 ID、数据源类型、每阶段延迟、LLM 用量和 Judge 状态。产品响应延迟与 Judge 耗时必须分开统计。

## 10. 完成定义（Definition of Done）

- 本文第 5 节所有硬门禁通过。
- 27 个历史失败样例均有测试覆盖、修复提交和复测证据。
- 30 条完整真实 E2E 连续运行三次，无空回答、无安全冲突、无跨样例记忆污染。
- 所有 Agent 和工具均返回统一协议，失败原因可追踪，状态与实际产物一致。
- 任意请求可以通过一个 `trace_id` 还原主请求、主 Agent、专业 Agent、工具、LLM 和后台写入的父子调用链。
- 报告明确标注真实、缓存、模拟和降级数据，不再把 mock AQI 表述为实时数据。
- 修复前后报告保留在 `reports/`，附差异摘要，能够量化质量、延迟、调用次数和 Token 成本变化。
- Docker 从干净缓存重新构建后仍能通过全部测试，镜像中不包含 `.env` 或其他密钥文件。
