# deploy 目录规范

生产部署配置。服务器端对应 `/opt/docx-check`（单机 Docker Compose + 系统级 Caddy）。

## 部署架构

```text
浏览器 ── HTTPS ──> Caddy(系统级) ── /api、/health ──> FastAPI(backend 容器) ──> PostgreSQL(postgres 容器)
                        │
                        ├── docx-check.prod.chatgqt.top        静态 /opt/docx-check/web（学生/教师端 SPA）
                        ├── admin.docx-check.prod.chatgqt.top  静态 /opt/docx-check/admin（管理端 SPA）
                        └── www.speedee.cn                     静态 /opt/hosting + 反代 127.0.0.1:8046（原 nginx 站点迁移）
```

- 镜像：`docker.gqt.plus/docx-check/docx-check-api`（zot，CI 推送；服务器匿名可拉取）
- 前端不在容器内：CI 构建 dist → 解压到 `/opt/docx-check/{web,admin}`，系统 Caddy 直接托管
- Caddy 为系统服务（非容器）：配置 `/etc/caddy/Caddyfile`，自动 HTTPS（Let's Encrypt）

## 目录内容

```text
deploy/
├── docker-compose.yml   # 生产 Compose（backend + postgres:17.11；CI 同步到服务器）
├── Caddyfile            # 系统 Caddy 配置（CI 同步到 /etc/caddy/Caddyfile）
├── .env.example         # 环境变量模板（提交；实际 .env 只在服务器）
└── AGENTS.md
```

## 部署方式

- `images.yml`：push main → 构建 backend 镜像并推送 zot + GHCR（tag = sha 与 latest）
- `deploy-production.yml`：手动触发（workflow_dispatch）→ 构建前端 → 上传配置/产物 → 激活配置（带备份回滚）→ 服务器登录 zot → 拉镜像 → 数据库备份 + 迁移 → 起 backend → 刷新 Caddy → 健康检查
- 首次部署前置（一次性，手工）：
  1. 服务器安装 Caddy、备份并停用 nginx
  2. `/opt/docx-check/.env`（按 `.env.example` 生成，600 权限）
  3. `sudo usermod -aG docker ubuntu`（CI 免 sudo 使用 docker；zot 登录由部署工作流自动完成）

## 常用命令（服务器）

```bash
cd /opt/docx-check
docker compose ps
docker compose logs -f backend
docker compose run --rm backend uv run python -m scripts.create_admin admin '<密码>' '管理员'
docker compose run --rm backend uv run alembic upgrade head
sudo systemctl reload caddy      # 改 Caddyfile 后
sudo caddy validate --config /etc/caddy/Caddyfile
```

## 注意

- `.env` 含密钥，永不提交；修改后端配置需同步 `backend/.env.example`
- 备份：nginx 原配置在 `~/backups/`；数据库 dump 在 `/opt/docx-check/backups/`
