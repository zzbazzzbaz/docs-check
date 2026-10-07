#!/bin/bash
# 验证 deploy 的 WPS 常驻服务：起服务 → 等健康 → exec 进去真取一次值。
#
# 和 ./run.sh 的区别：run.sh 是 `docker run` 一次性执行，环境变量由 entrypoint 继承；
# 这条测的是 compose 长驻 + `docker exec`，exec 的进程只认镜像 ENV。
set -uo pipefail
cd "$(dirname "$0")"

COMPOSE="docker compose -f ../deploy/docker-compose.dev.yml"
CONTAINER=gqt_thesis_wps

step() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }

mkdir -p ../deploy/data/in ../deploy/data/out
cp -n corpus/*.docx ../deploy/data/in/ 2>/dev/null || true

step "启动服务"
$COMPOSE up -d || exit 1

step "等健康检查"
for _ in $(seq 1 40); do
    st=$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo none)
    printf '  %s\n' "$st"
    [ "$st" = healthy ] && break
    if [ "$st" = unhealthy ]; then
        docker inspect --format '{{range .State.Health.Log}}{{.ExitCode}}: {{.Output}}{{end}}' \
            "$CONTAINER" | tail -2
        exit 1
    fi
    sleep 10
done

step "exec 进容器取值"
docker cp docxfmt/wps.py "$CONTAINER":/tmp/wps.py
$COMPOSE exec -T wps python3 /tmp/wps.py --outdir /out /in/*.docx
