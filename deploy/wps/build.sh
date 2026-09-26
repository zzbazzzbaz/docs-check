#!/bin/bash
# 构建无头 WPS 镜像。用法与说明见 ../README.md
set -euo pipefail
cd "$(dirname "$0")"

WPS_VER="${WPS_VER:-12.1.2.28080}"
WPS_DEB="wps-office_${WPS_VER}_amd64.deb"
IMAGE="${WPS_IMAGE:-thesis-format-review/wps}"
TAG="${IMAGE_TAG:-dev}"
MIRROR="${WPS_MIRROR:-https://mirrors.aliyun.com/ubuntukylin/pool/partner}"

if [ ! -s "cache/${WPS_DEB}" ]; then
    echo "→ 下载 ${WPS_DEB}（约 545MB）"
    mkdir -p cache
    curl -L -C - --retry 3 -o "cache/${WPS_DEB}" "${MIRROR}/${WPS_DEB}"
else
    echo "→ 已缓存 cache/${WPS_DEB}"
fi

echo "→ 构建 ${IMAGE}:${TAG}"
docker build --platform linux/amd64 \
    --build-arg "WPS_DEB=${WPS_DEB}" \
    -t "${IMAGE}:${TAG}" \
    -t "${IMAGE}:${WPS_VER}" \
    "$@" \
    .

echo "完成：${IMAGE}:${TAG} / ${IMAGE}:${WPS_VER}"
