# KKManus Backend

KKManus 后端负责认证、Agent Run 生命周期、Dramatiq 异步执行、Redis/SSE 通信、Google ADK 适配、工具调用、三层记忆和运行质量评估。

## 技术栈

- FastAPI
- PostgreSQL / pgvector
- Redis / Dramatiq
- Google ADK
- LiteLLM

## 本地环境

推荐使用 Python 3.11 和独立的 `kk-manus` Conda 环境：

```bash
conda create -n kk-manus python=3.11
conda activate kk-manus
pip install -r requirements.txt
cp .env.example .env
```

配置 PostgreSQL、Redis 和模型供应商后，启动 API：

```bash
python api.py
```

另开终端启动唯一的 Dramatiq Worker：

```bash
conda activate kk-manus
python -m dramatiq --skip-logging --processes 1 --threads 4 run_agent_background
```

不要同时使用终端、`nohup` 和 launchctl 启动多个 Worker。同一个运行任务虽然有 Redis 幂等锁，但旧 Worker 仍可能抢先消费新任务。

## 数据库

SQL 迁移位于：

```text
supabase/migrations/
```

语义长期记忆需要 PostgreSQL pgvector，并使用 1024 维向量字段。`.env.example` 默认关闭向量记忆；数据库和 Embedding 凭据就绪后再显式开启。

## 测试

```bash
python -m unittest discover -s tests
```

与当前工程化扩展直接相关的代码：

```text
agent/run.py                                           Agent 执行主链路
agent/agent_run_eval.py                                Agent Run 运行评估
agent/github_repo_interview_conversation_summary.py    面试练习总结
agent/tools/github_repo_interview_workflow_tool.py      受控 GitHub 面试工作流
agent/tools/github_repo_interview_session_memory.py     会话短期记忆
agent/tools/github_repo_interview_vector_memory.py      pgvector 长期记忆
```
