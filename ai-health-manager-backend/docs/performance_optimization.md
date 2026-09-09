# Phase 4 性能优化文档

本文档描述了AI健康管家的性能优化实现，包括Redis缓存、数据库查询优化和Celery异步任务。

## 1. Redis缓存

### 1.1 架构设计

```
┌─────────────────┐      ┌──────────────┐      ┌─────────────┐
│   API Endpoint  │──────▶│ Cache Layer  │──────▶│  Redis      │
└─────────────────┘      └──────────────┘      └─────────────┘
                                │
                                ▼
                        ┌──────────────┐
                        │ Agent/DB     │
                        └──────────────┘
```

### 1.2 缓存配置

**文件**: `app/core/cache.py`

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `DEFAULT_TTL` | 300s (5分钟) | 默认缓存时间 |
| `AGENT_RESULT_TTL` | 300s (5分钟) | Agent结果缓存 |
| `USER_PROFILE_TTL` | 3600s (1小时) | 用户资料缓存 |
| `RAG_RESULT_TTL` | 600s (10分钟) | RAG检索缓存 |

### 1.3 使用示例

**装饰器方式**:

```python
from app.core.cache import cached, cached_agent_result

@cached(ttl=300, key_prefix="api")
async def get_data(user_id: str):
    return await expensive_query(user_id)

@cached_agent_result()
async def analyze_nutrition(user_id: str, description: str):
    return await agent.process(description)
```

**直接API方式**:

```python
from app.core.cache import cache_manager

# 存储缓存
await cache_manager.set("key", value, ttl=300)

# 获取缓存
value = await cache_manager.get("key")

# 删除缓存
await cache_manager.delete("key")
```

## 2. 数据库查询优化

### 2.1 索引管理

**文件**: `app/db/optimizations.py`

| 表名 | 索引字段 | 类型 | 用途 |
|------|----------|------|------|
| `users` | `email` | UNIQUE | 用户登录 |
| `users` | `created_at` | INDEX | 用户统计 |
| `user_profiles` | `user_id` | UNIQUE | 用户资料查询 |
| `health_records` | `user_id` + `record_type` | INDEX | 健康记录查询 |
| `health_records` | `record_date` | INDEX | 日期范围查询 |
| `chat_sessions` | `user_id` + `updated_at` | INDEX | 会话列表 |
| `chat_messages` | `session_id` + `created_at` | INDEX | 消息历史 |

### 2.2 使用索引管理器

**创建索引**:

```python
from app.db.optimizations import IndexManager

# 创建单个索引
await IndexManager.create_index(
    table_name="health_records",
    columns=["user_id", "record_date"],
    unique=False
)

# 创建所有推荐索引
results = await IndexManager.setup_recommended_indexes()
```

**查询优化器**:

```python
from app.db.optimizations import QueryOptimizer

# 优化用户查询（避免N+1）
user = await QueryOptimizer.optimize_user_query(session, user_id)

# 优化健康数据查询
query = QueryOptimizer.optimize_health_data_query(
    session=session,
    user_id=user_id,
    record_type="steps",
    start_date="2024-01-01",
    end_date="2024-01-31"
)
```

### 2.3 运行索引设置脚本

```bash
python scripts/setup_database.py
```

输出示例：
```
============================================================
AI Health Manager - Database Setup
============================================================

1. Initializing database...
   Database initialized ✓

2. Checking current indexes...

3. Setting up recommended indexes...
   ✓ Index setup complete: 10/10 indexes ready

✓ Database setup completed successfully!
```

## 3. Celery异步任务

### 3.1 架构设计

```
┌─────────────────┐      ┌──────────────┐      ┌─────────────┐
│   API Request   │──────▶│ Celery       │──────▶│ Redis       │
└─────────────────┘      │ Broker       │      │ (Broker)    │
                         └──────────────┘      └──────┬──────┘
                                                      │
                         ┌──────────────┐             │
                         │ Celery       │◀────────────┘
                         │ Worker       │      (Task Queue)
                         └──────┬───────┘
                                │
                         ┌──────▼───────┐
                         │ Task Result  │
                         │ (Redis)      │
                         └──────────────┘
```

### 3.2 配置

**文件**: `app/core/celery.py`

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `broker_url` | redis://localhost:6379/1 | 消息队列 |
| `result_backend` | redis://localhost:6379/2 | 结果存储 |
| `timezone` | Asia/Shanghai | 时区 |
| `task_time_limit` | 3600s | 任务超时 |
| `worker_concurrency` | 4 | Worker并发数 |

### 3.3 任务队列

| 队列名 | 用途 | 优先级 |
|--------|------|--------|
| `default` | 默认任务 | 中 |
| `health` | 健康数据处理 | 高 |
| `agent` | Agent处理 | 高 |
| `notification` | 通知发送 | 低 |

### 3.4 使用示例

**定义任务**:

```python
from app.core.celery import celery_app

@celery_app.task(bind=True, max_retries=3)
def my_task(self, arg1, arg2):
    try:
        # Task logic
        result = process_data(arg1, arg2)
        return result
    except Exception as exc:
        # Retry on failure
        raise self.retry(exc=exc, countdown=60)
```

**调用任务**:

```python
# Async call
task = my_task.delay(arg1="value1", arg2="value2")
print(f"Task ID: {task.id}")

# Check result
from app.core.celery import get_task_info
info = get_task_info(task.id)
print(f"Status: {info['status']}")

# Revoke task
from app.core.celery import revoke_task
revoke_task(task.id, terminate=True)
```

### 3.5 启动Worker

```bash
# Start worker (all queues)
python scripts/start_celery.py worker

# Start worker (specific queue)
celery -A app.core.celery:celery_app worker --queues=health,agent --loglevel=info

# Start scheduler (celery beat)
python scripts/start_celery.py beat

# Start monitoring (flower)
python scripts/start_celery.py flower
```

### 3.6 内置任务

**Health Tasks** (`app/core/tasks/health.py`):
- `import_health_data` - 导入健康数据
- `generate_health_report` - 生成健康报告
- `aggregate_health_data` - 聚合健康数据

**Agent Tasks** (`app/core/tasks/agent.py`):
- `process_nutrition_async` - 异步营养分析
- `process_environment_async` - 异步环境查询
- `process_exercise_async` - 异步运动计划

**Notification Tasks** (`app/core/tasks/notification.py`):
- `send_health_reminder` - 发送健康提醒
- `process_scheduled_reminders` - 处理计划提醒
- `send_daily_health_digest` - 发送每日健康摘要

## 4. 性能监控

### 4.1 日志记录

所有性能关键操作都有详细的日志记录：

```python
# 缓存操作
logger.info(f"[cache] Hit for key: {cache_key}")
logger.warning(f"[cache] Miss for key: {cache_key}")

# 数据库查询
logger.info(f"[db] Query executed in {elapsed_time}ms")
logger.warning(f"[db] Slow query detected: {query}")

# 任务执行
logger.info(f"[task] Task {task_id} completed in {duration}s")
logger.error(f"[task] Task {task_id} failed: {error}")
```

### 4.2 指标收集

可以通过以下方式收集性能指标：

```python
from app.core.cache import cache_manager
from app.db.optimizations import ConnectionPoolManager

# 缓存命中率
cache_stats = await cache_manager.get_stats()
print(f"Cache hit rate: {cache_stats['hit_rate']}%")

# 连接池状态
pool_status = await ConnectionPoolManager.get_pool_status()
print(f"Active connections: {pool_status['checked_out']}")
```

## 5. 部署建议

### 5.1 生产环境配置

```python
# config.py

# Redis配置
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD')

# Celery配置
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2')
```

### 5.2 Docker Compose配置

```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  celery_worker:
    build: .
    command: celery -A app.core.celery:celery_app worker --loglevel=info
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/2
    depends_on:
      - redis

  celery_beat:
    build: .
    command: celery -A app.core.celery:celery_app beat --loglevel=info
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/1
      - CELERY_RESULT_BACKEND=redis://redis:6379/2
    depends_on:
      - redis

volumes:
  redis_data:
```

## 6. 总结

Phase 4性能优化完成了以下核心功能：

1. **Redis缓存系统**
   - 支持装饰器和直接API两种使用方式
   - 分级TTL策略
   - 集成Agent端点

2. **数据库优化**
   - 索引管理器
   - 查询优化器
   - 自动索引设置脚本

3. **Celery异步任务**
   - 多队列支持
   - 内置任务类型
   - 监控和管理工具

这些优化将显著提升系统的响应速度和并发处理能力。