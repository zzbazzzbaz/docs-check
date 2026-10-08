FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_DEV=1

# 目录布局与仓库一致：/srv/backend 与 /srv/thesis-check（uv.lock 的可编辑依赖 ../thesis-check）
# 构建上下文 = 仓库根目录：docker build -f backend/Dockerfile .
WORKDIR /srv

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/

COPY backend/pyproject.toml backend/uv.lock ./backend/
COPY thesis-check ./thesis-check
WORKDIR /srv/backend
RUN uv sync --locked --no-dev

COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/scripts ./scripts
COPY backend/app ./app

EXPOSE 8000

CMD ["uv", "run", "fastapi", "run", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
