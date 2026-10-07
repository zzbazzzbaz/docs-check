# Backend AGENTS

## 命令

- 安装：`uv sync`
- 配置：所有字段必填、无代码内默认值，统一维护在 `.env`（新环境复制 `.env.example`）；改配置须同步 `.env` 与 `.env.example`
- 初始化数据库/迁移：`uv run alembic upgrade head`；改模型后 `uv run alembic revision --autogenerate -m "描述"` 生成迁移（手校 FK/索引/默认值）
- 创建管理员：`uv run python -m scripts.create_admin <username> [password] [name]`
- 开发种子数据（幂等，仅开发工具）：`uv run python -m scripts.dev_seed`
- Lint：`uv run ruff check .` / `uv run ruff format --check .`
- 类型：`uv run ty check`
- 测试：`uv run pytest`（读 `.env`，连 `DATABASE_URL` 派生的 `<db>_test` 库，自动建库 + 每次重建表；禁止在测试里硬编码 `os.environ`）
- 启动：`uv run fastapi run`（entrypoint 见 pyproject.toml）；文件存腾讯云 COS（`COS_*` 全必填，无本地存储；上传三段式 / 下载 307 见下）
- 对象存储冒烟（真实桶，读 `.env`）：`uv run python -m scripts.cos_smoke --username <学生账号> --password <密码>`

## 分层（单向，禁止反向 import）

```text
core → infrastructure → services → api
```

- `api`：解析参数、调 service、异常转 HTTP（DomainError → 状态码统一映射在 `app/api/error_handlers.py`，route 不写 try/except）、返回 schema。禁止业务判断、禁止写查询。
- `services`：领域规则、事务、授权（含 `services/tasks/review_worker.py` 的任务消费）。禁止 HTTP 概念（HTTPException、Request、Depends）；业务异常抛 `app/services/errors.py` 的 DomainError（带稳定 `code`，前端据此映射文案）。
- `infrastructure`：数据库、文件存储（`storage/base.py` 协议 + `storage/cos.py` 唯一实现：预签名 / HEAD / 转正 / 读写 / best-effort 删除，无本地后端）、审核引擎适配（`review/engine.py` 是唯一 import `thesischeck` 的模块）。禁止业务规则，禁止依赖 `services` / `api`。
- `core`：配置、密钥、令牌。禁止依赖任何上层。

## 业务要点（10.7 Web 层）

- 三角色：`student` / `teacher` / `admin`；无自助注册（旧 register/角色接口已删），管理员由脚本创建，学生/教师由管理端创建。
- 强制改密门禁：`CurrentUserDep`（宽，仅 `/users/me*` 可用）/ `CurrentReadyUserDep`（严，其余业务接口；未改密 403 `password_required_change`）。
- 提交是**异步**的：上传三段式（`POST /submissions/upload-url` 签发预签名 PUT → 客户端直传 COS → `POST /submissions` JSON 确认，202 `pending`），`submissions` 单表状态机（status/attempts/started_at）+ 进程内 worker（单实例）领取执行；状态 `pending → processing → success / failed`，前端轮询详情。
- worker 领取用 `FOR UPDATE SKIP LOCKED`；坏文档不重试（直接 failed + 清理文件），基础设施异常最多 `TASK_MAX_ATTEMPTS` 次；启动恢复 `processing→pending`，运行期 stale 兜底。
- 下载鉴权：学生本人 / 名下且启用的教师；管理员不可见提交内容。下载返回 **307 预签名**（`response-content-disposition` 中文名走 `filename*`），字节从 COS 直达。
- 测试**不启动**后台 worker（测试 app 不跑 lifespan），构造 `ReviewWorker` 后手动 `await worker.process_next()` 驱动（确定性）；测试 docx 样本用 `tests/factories.py` 手工拼字节，不提交二进制语料。
