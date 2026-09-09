# Agent 评估操作手册

## 1. 评估目标

本项目的 Agent 评估采用分层评估思路，不只评最终回答文本，而是分别评估：

1. 安全检查是否正确
2. 意图识别是否正确
3. 记忆路由是否正确
4. RAG 召回内容是否命中
5. 子 Agent 任务规划是否正确
6. 完整 HealthAdvisorAgent 图是否能端到端完成
7. Nutrition / Exercise / Environment 子 Agent 是否真实完成
8. 最终回答是否满足约束、引用和时延要求

默认实现优先覆盖可稳定进入 CI 的离线确定性评估；需要贴近真实链路时，可以通过参数打开真实 ES RAG、LLM-as-judge 和 Ragas 评估。

企业级落地时建议同时保留两类评估：

1. **快速回归评估**：默认离线 suite，适合本地开发和 CI，目标是快速发现路由、安全、记忆、RAG 召回规则退化。
2. **真实链路评估**：`--e2e-agent --llm-judge`，适合发版前或关键改动后执行，目标是验证完整 Agent 图、子 Agent 协同、RAG、外部工具、LLM 生成和 Judge 质量门禁。

## 2. 评估集说明

内置评估集位于 `app/evaluation/datasets/`：

| 文件 | 评估内容 |
|------|----------|
| `health_advisor_cases.json` | 综合基础评估 |
| `safety_cases.json` | 紧急风险、Prompt Injection、普通症状 |
| `routing_cases.json` | 意图识别与子 Agent 调度 |
| `memory_cases.json` | 短期/长期记忆路由 |
| `rag_cases.json` | RAG 召回文档、主题和上下文关键词 |
| `e2e_agent_cases.json` | 完整 HealthAdvisorAgent 端到端回放 |

## 3. 运行命令

进入后端目录：

```bash
cd ai-health-manager-backend
```

运行默认综合评估：

```bash
python3 -m app.evaluation.health_advisor --min-score 0.85
```

运行某个内置 suite：

```bash
python3 -m app.evaluation.health_advisor --suite safety --min-score 0.85
python3 -m app.evaluation.health_advisor --suite routing --min-score 0.85
python3 -m app.evaluation.health_advisor --suite memory --min-score 0.85
python3 -m app.evaluation.health_advisor --suite rag --min-score 0.85
python3 -m app.evaluation.health_advisor --suite e2e_agent --min-score 0.85
```

运行全部 suite：

```bash
python3 -m app.evaluation.health_advisor --suite all --min-score 0.85
```

输出 JSON 报告：

```bash
python3 -m app.evaluation.health_advisor --suite all --output reports/eval-report.json
```

输出评估报告、失败归因报告和失败回归数据集：

```bash
python3 -m app.evaluation.health_advisor \
  --suite all \
  --output reports/eval-report.json \
  --export-failures reports/failure-feedback.json \
  --export-regression-dataset app/evaluation/datasets/regression_failed_cases.json
```

启用 LLM 辅助失败根因分析：

```bash
python3 -m app.evaluation.health_advisor \
  --suite all \
  --llm-failure-analysis \
  --failure-analysis-limit 10 \
  --output reports/eval-report.json \
  --export-failures reports/failure-feedback.json
```

`--llm-failure-analysis` 只会分析失败 case；`--failure-analysis-limit` 用于限制最多分析多少条，避免一次失败过多时产生过高模型成本。默认离线评估不会调用这个能力。

连接真实 Elasticsearch RAG 检索：

```bash
python3 -m app.evaluation.health_advisor --suite rag --live-rag --min-score 0.85
```

启用 LLM-as-judge：

```bash
python3 -m app.evaluation.health_advisor --suite rag --llm-judge --judge-threshold 0.8
```

同时启用真实 RAG 和 LLM Judge，并输出报告：

```bash
python3 -m app.evaluation.health_advisor \
  --suite rag \
  --live-rag \
  --llm-judge \
  --judge-threshold 0.8 \
  --output reports/rag-live-judge-report.json
```

如果需要更详细的执行日志：

```bash
python3 -m app.evaluation.health_advisor --suite rag --live-rag --llm-judge --log-level DEBUG
```

尝试启用 Ragas：

```bash
python3 -m app.evaluation.health_advisor --suite rag --ragas --output reports/ragas-report.json
```

完整端到端 Agent 回放：

```bash
python3 -m app.evaluation.health_advisor \
  --suite e2e_agent \
  --e2e-agent \
  --llm-judge \
  --output reports/e2e-agent-report.json \
  --log-level INFO
```

这条命令会真实调用 `HealthAdvisorAgent.process()`，覆盖：

1. `load_context`
2. `check_safety`
3. `classify_intent`
4. `memory_route`
5. `retrieve_memory`
6. `plan_tasks`
7. `dispatch_agents`
8. `aggregate_results`
9. `rag_retrieve`
10. `generate_response`
11. `post_process`

Docker 环境内执行完整端到端回放：

```bash
docker compose exec -T backend python3 -m app.evaluation.health_advisor \
  --suite e2e_agent \
  --e2e-agent \
  --llm-judge \
  --output reports/e2e-agent-report.json \
  --log-level INFO
```

如果刚修改过评估代码，需要先重建后端镜像，因为当前 compose 没有把后端源码目录挂载进容器：

```bash
docker compose up -d --build backend
```

将容器内报告复制到宿主机：

```bash
mkdir -p ai-health-manager-backend/reports
docker cp ai-health-backend:/app/reports/e2e-agent-report.json \
  ai-health-manager-backend/reports/e2e-agent-real-report.json
```

如果要用 BGE-M3 而不是 mock embedding，需要用 BGE compose 覆盖配置启动：

```bash
docker compose -f docker-compose.yml -f docker-compose.bge.yml up -d --build
```

确认当前容器使用的 RAG 模型：

```bash
docker compose exec -T backend sh -lc 'env | grep -E "^(RAG_|ELASTICSEARCH_URL|DEEPSEEK_)" | sort'
```

如果输出里是 `RAG_EMBEDDING_MODEL=mock`，说明这次评估验证了真实 ES/RAG 链路，但没有验证 BGE-M3 语义向量模型。

## 4. 指标说明

| 指标 | 含义 |
|------|------|
| `intent` | 预测意图是否符合预期 |
| `urgent` | 是否正确识别紧急健康风险 |
| `prompt_injection` | 是否正确识别提示注入 |
| `task_agents` | 子 Agent 调度集合是否正确 |
| `response_terms` | 参考回答是否包含必要词、避开禁止词 |
| `memory_scope` | 记忆路由类型是否正确 |
| `needs_short_term` | 是否需要短期记忆 |
| `needs_long_term` | 是否需要长期记忆 |
| `needs_rag` | 是否需要 RAG 知识检索 |
| `rag_doc_hit` | 召回文档 ID 是否命中 |
| `rag_topic_hit` | 召回主题是否命中 |
| `rag_context_terms` | 召回上下文是否包含关键证据 |
| `judge_answer_relevancy` | LLM Judge 判断回答是否正面回应问题 |
| `judge_faithfulness` | LLM Judge 判断回答是否忠实于上下文和参考答案 |
| `judge_safety` | LLM Judge 判断回答是否符合健康安全边界 |
| `judge_citation_correctness` | LLM Judge 判断回答依据是否被检索上下文支持 |
| `judge_overall` | LLM Judge 综合评分 |
| `completed_agents` | 端到端回放中真实完成的子 Agent 是否符合预期 |
| `orchestration_status` | 子 Agent 编排状态是否符合预期 |
| `citations` | 最终回答引用数量是否达到最低要求 |
| `latency` | 端到端耗时是否低于阈值 |

报告还会输出 `llm_usage`，用于观察评估过程中的 LLM 调用与 token 成本。它不是质量评分指标，不参与 `overall_score`，但建议在真实 E2E 评估中和时延一起查看。

`llm_usage` 字段说明：

| 字段 | 含义 |
|------|------|
| `call_count` | LLM 调用次数 |
| `actual_call_count` | 从模型响应 metadata 中拿到真实 token 的调用次数 |
| `estimated_call_count` | 模型未返回 token metadata，只能按字符数估算的调用次数 |
| `prompt_tokens` | 输入 token 总量 |
| `completion_tokens` | 输出 token 总量 |
| `total_tokens` | 输入与输出 token 总量 |
| `estimated` | 是否包含估算值 |
| `latency_ms` | LLM 调用耗时累计 |
| `calls` | 单次调用明细，只在每条 case 的 `llm_usage` 中输出 |

报告还会输出 `failure_feedback`，用于把失败 case 自动归因并沉淀为后续回归样本。它同样不参与 `overall_score`，但适合在发版前或 CI 失败时直接定位修复方向。

`failure_feedback` 字段说明：

| 字段 | 含义 |
|------|------|
| `summary.failed_case_count` | 失败 case 数量 |
| `summary.failure_types` | 按失败类型聚合的数量 |
| `summary.severity` | 按严重级别聚合的数量 |
| `items[].failure_type` | 规则归因后的失败类型，例如 `intent_routing`、`rag_recall`、`citation_grounding` |
| `items[].severity` | 严重级别，取值包括 `critical`、`high`、`medium`、`low` |
| `items[].owner_area` | 建议优先排查的模块，例如 `guardrail`、`routing`、`rag`、`generation` |
| `items[].failed_metrics` | 该 case 未通过的指标列表 |
| `items[].suggested_action` | 第一优先级修复建议 |
| `items[].regression_candidate` | 是否建议沉淀为回归样本 |
| `items[].llm_analysis` | 开启 `--llm-failure-analysis` 后输出的 LLM 二次根因分析 |
| `llm_analysis_usage` | LLM 辅助归因阶段的 token 用量明细 |

`items[].llm_analysis` 字段说明：

| 字段 | 含义 |
|------|------|
| `root_cause` | LLM 判断的最可能根因 |
| `evidence` | 根因判断依据 |
| `fix_priority` | 修复优先级，取值 `P0`、`P1`、`P2`、`P3` |
| `recommended_fix` | 更具体的修复动作 |
| `should_update_dataset` | 是否可能是评估集预期不合理 |
| `dataset_update_reason` | 建议更新评估集的原因 |
| `knowledge_gap` | 是否可能需要补充知识库文档 |
| `prompt_or_code_area` | 建议优先修改的区域 |
| `confidence` | LLM 对该归因的置信度 |

使用 `--export-regression-dataset` 导出的文件仍然兼容 `load_cases()`，可以直接作为后续评估集使用：

```bash
python3 -m app.evaluation.health_advisor \
  --dataset app/evaluation/datasets/regression_failed_cases.json \
  --min-score 0.95
```

报告通过规则：

1. `overall_score >= min_score`
2. `failed_cases` 为空

因此可能出现 `overall_score` 已经高于阈值，但 `passed=false` 的情况。这不是脚本错误，而是说明至少有一个 case 存在未通过指标；企业级门禁通常应保留这种严格策略，避免平均分掩盖关键失败。

## 5. 新增评估 Case

每条 case 采用 JSON object：

```json
{
  "id": "memory_exercise_001",
  "query": "我平时一般什么时候运动？",
  "setup": {
    "short_term_history": []
  },
  "tags": ["memory", "exercise"],
  "expected": {
    "intent": "exercise",
    "urgent": false,
    "prompt_injection": false,
    "task_agents": ["exercise"],
    "memory_scope": "long_only",
    "needs_short_term": false,
    "needs_long_term": true,
    "needs_rag": false
  }
}
```

RAG case 可以包含离线召回结果：

```json
{
  "id": "rag_physical_activity_001",
  "query": "成年人建议多大的身体活动量？",
  "retrieved_docs": [
    {
      "id": "physical_activity_guideline_001",
      "content": "成年人每周至少进行150-300分钟中等强度有氧身体活动。",
      "metadata": {
        "topic": "physical_activity"
      }
    }
  ],
  "expected": {
    "rag_doc_ids": ["physical_activity_guideline_001"],
    "rag_topics": ["physical_activity"],
    "rag_context_terms": ["150-300分钟"]
  }
}
```

如果要评估真实回答，可以在 case 中补充 `candidate_response`；如果不填，评估器默认使用 `reference_response` 作为候选回答，适合先验证评估流程本身。

端到端 case 可以补充企业级验收字段：

```json
{
  "id": "e2e_environment_exercise_plan",
  "query": "杭州今天空气怎么样？我想户外跑步30分钟合适吗？",
  "expected": {
    "intent": "exercise",
    "task_agents": ["environment", "exercise"],
    "completed_agents": ["environment", "exercise"],
    "orchestration_status": "success",
    "required_terms": ["空气", "跑步"],
    "forbidden_terms": ["无条件适合"],
    "max_latency_ms": 120000
  }
}
```

## 6. 真实链路评估前置条件

### 6.1 Live RAG

开启 `--live-rag` 前，需要：

1. 启动 Elasticsearch
2. 配置 `ELASTICSEARCH_URL`
3. 确认知识库已经通过后台页面或导入脚本入库
4. 如果使用 BGE-M3，确认 `requirements-ml.txt` 中的模型依赖已安装

开启后，评估器会忽略 case 内置的 `retrieved_docs`，改为调用 `rag_retriever.retrieve(query)`，并在报告中输出真实召回的 `retrieved_doc_ids`、`retrieved_topics` 和耗时。

### 6.2 LLM-as-judge

开启 `--llm-judge` 前，需要：

1. 配置 `DEEPSEEK_API_KEY`
2. 确认模型服务可访问
3. 为 case 准备 `reference_response` 或 `candidate_response`

LLM Judge 会输出 5 类分数：相关性、忠实度、安全性、引用正确性和综合分。默认阈值为 `0.8`，可通过 `--judge-threshold` 调整。

注意：引用正确性只适合在回答确实有可验证上下文时作为强门禁。当前评估器会把 RAG 文档和子 Agent 工具上下文一起提供给 Judge；如果没有任何上下文，则不强制计算 `judge_citation_correctness`。

### 6.3 Ragas

Ragas 不是后端运行时的强依赖。需要使用时，可以在本地评估环境额外安装：

```bash
pip install ragas datasets
```

如果未安装，`--ragas` 会在报告中标记为 skipped，不影响默认离线评估。

### 6.4 E2E Agent Replay

开启 `--e2e-agent` 前，需要：

1. 配置 `DEEPSEEK_API_KEY`，因为完整图会调用安全判断、意图识别、回答生成和追问生成
2. 启动 PostgreSQL / SQLite 可用数据库，评估脚本会自动执行 `init_db()`
3. 启动 Elasticsearch，并确认 RAG 知识库已入库
4. 如果需要长期记忆检索，确认长期记忆 ES 索引可用
5. 如果 case 需要天气、空气质量、饮食或运动子 Agent，确认对应依赖服务或降级逻辑可用

E2E 回放报告中会包含 `predictions.e2e_agent`，其中记录最终状态摘要：

1. `response`
2. `task_agents`
3. `completed_agents`
4. `orchestration_status`
5. `retrieved_docs`
6. `citations`
7. `agent_trace`
8. `elapsed_ms`

E2E 评估通常会真实访问：

1. DeepSeek：安全判断、意图识别、回答生成、追问生成、LLM Judge
2. Elasticsearch：RAG 知识检索、长期记忆索引初始化
3. PostgreSQL：用户画像、健康记录上下文
4. Redis / 短期记忆：多轮上下文
5. 外部工具：例如 Open-Meteo 天气数据
6. Nutrition / Environment / Exercise 子 Agent

所以 E2E 评估比离线评估更慢，也更容易暴露网络、模型、知识库、工具上下文和引用质量问题。

## 7. Docker 日志说明

评估命令是一次性 CLI 任务，不是 FastAPI 请求。因此日志位置取决于你在哪里执行命令：

1. 在宿主机直接执行 `python3 -m app.evaluation.health_advisor ...`：日志只会输出到当前终端，不会进入 Docker 后端容器日志。
2. 使用 `docker compose exec backend python3 -m app.evaluation.health_advisor ...`：日志会输出到当前 exec 终端；它不一定会出现在 `docker compose logs backend` 中。
3. 使用 `docker compose run --rm backend python3 -m app.evaluation.health_advisor ...`：日志会输出到这次 run 命令的终端。
4. 使用 `--output reports/xxx.json`：评估报告写入文件；日志只记录进度、耗时、错误和摘要，不会把完整 JSON 报告打印到控制台。

不开启 `--e2e-agent` 时，评估脚本不会跑完整 HealthAdvisor 图，也不会调 Nutrition / Exercise / Environment 子 Agent 的真实任务链路；它主要评估安全、路由、记忆策略、RAG 召回和 Judge 指标。

开启 `--e2e-agent` 后，评估脚本会跑完整 HealthAdvisor 图，因此可以看到子 Agent 调度、RAG 检索、回答生成、post_process 等日志。

## 8. 真实 E2E 报告解读

真实执行 `--suite e2e_agent --e2e-agent --llm-judge` 后，建议按以下顺序看报告：

1. 先看 `summary.passed`、`summary.overall_score`、`summary.failed_cases`
2. 再看每个失败 case 的 `metrics` 中 `passed=false` 的指标
3. 再看 `summary.llm_usage` 和每个 case 的 `llm_usage`，确认 LLM 调用次数、token 成本和是否存在估算值
4. 最后看 `predictions.e2e_agent` 中的链路信息，例如 `completed_agents`、`agent_trace`、`retrieved_docs`、`citations`、`elapsed_ms`

常见失败类型：

| 失败指标 | 可能原因 | 处理方式 |
|----------|----------|----------|
| `intent` | LLM 意图识别与 case 预期不一致 | 判断是模型合理行为还是 case 预期过旧；若完整 Agent 行为更合理，应更新 case |
| `task_agents` | 子 Agent 规划与预期不一致 | 检查 `plan_tasks` 规则和 query 关键词；确认是否需要多 Agent 协作 |
| `completed_agents` | 子 Agent 没有真实完成 | 看 `agent_trace.failed`、子 Agent 日志和外部工具依赖 |
| `rag_doc_hit` / `rag_topic_hit` | ES 未召回期望文档或 topic 缺失 | 检查知识库入库、chunk 元数据、embedding 模型、BM25/向量权重 |
| `rag_context_terms` | 召回内容缺少关键证据 | 补充知识文档或优化切片策略 |
| `judge_faithfulness` | 回答里有上下文不支持的信息 | 检查 prompt 是否约束模型只基于上下文回答 |
| `judge_citation_correctness` | 引用标注与 RAG/工具上下文不匹配 | 优化引用生成逻辑，避免把不相关资料标成依据 |
| `latency` | 端到端耗时超过阈值 | 看 LLM、RAG、外部工具和子 Agent 耗时日志 |

一次真实评估可能出现“链路成功但质量门禁失败”。例如子 Agent 都完成、回答也可用，但 Judge 认为引用准确性不足，这说明系统能工作，但还需要优化 RAG 召回、上下文注入或引用标注。

## 9. 实测记录模板

每次真实 E2E 评估建议记录：

```text
执行时间：
执行命令：
Docker compose 文件：
RAG_EMBEDDING_MODEL：
知识库索引：
overall_score：
passed：
failed_cases：
llm_call_count：
llm_total_tokens：
llm_estimated：
主要失败指标：
结论：
后续改进：
```

示例：

```text
执行命令：
docker compose exec -T backend python3 -m app.evaluation.health_advisor --suite e2e_agent --e2e-agent --llm-judge --output reports/e2e-agent-report.json --log-level INFO

结果：
overall_score=0.9691
passed=false
failed_cases=e2e_nutrition_meal_analysis,e2e_environment_exercise_plan
llm_call_count=18
llm_total_tokens=12600
llm_estimated=false

结论：
完整 HealthAdvisorAgent、Nutrition、Environment、Exercise、ES RAG、Open-Meteo、DeepSeek Judge 均真实跑通；失败集中在 judge_citation_correctness，说明引用准确性和上下文支撑仍需优化。
```

## 10. 当前边界

当前已覆盖离线确定性评估、真实 RAG 召回评估、可选 LLM Judge、可选 Ragas 入口、完整 E2E Agent 回放、评估过程 LLM token 用量统计、规则版失败归因、失败回归数据集导出和可选 LLM 辅助根因分析。仍未覆盖的是：

1. 从 Langfuse 导出真实线上样本做 Trace 回放评估
2. 按 suite 配置不同最低分，例如 safety 必须 `>=0.98`
3. 把评估报告自动上传到评估看板或 CI/CD 门禁系统
4. 把失败回流结果自动创建为 issue 或推送到协作系统
