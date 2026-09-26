#!/bin/bash
# 一键：自研 + foss 本地跑 → WPS 容器跑 → 三方对账
#
#   ./run.sh                       # 全语料
#   ./run.sh corpus/某篇.docx      # 指定文件（须在 corpus/ 下）
set -euo pipefail
cd "$(dirname "$0")"

IMAGE="${WPS_IMAGE:-thesis-format-review/wps:dev}"
mkdir -p out

if [ "$#" -gt 0 ]; then
    TARGETS=("$@")
else
    TARGETS=(corpus/*.docx)
fi
IN_NAMES=()
for p in "${TARGETS[@]}"; do
    IN_NAMES+=("/in/$(basename "$p")")
done
printf '%s\n' "${IN_NAMES[@]}" > out/wps_paths.txt

echo "── 1/4 自研 + foss（本地，${#TARGETS[@]} 篇）──"
uv run --quiet python -m docxfmt.own "${TARGETS[@]}"
uv run --quiet python -m docxfmt.foss "${TARGETS[@]}"
uv run --quiet python -m docxfmt.own_pages "${TARGETS[@]}"
uv run --quiet python -m docxfmt.own_textbox "${TARGETS[@]}"
uv run --quiet python -m docxfmt.index "${TARGETS[@]}"
uv run --quiet python -m docxfmt.own_borders "${TARGETS[@]}"

echo "── 2/4 准备 WPS 镜像：$IMAGE ──"
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "   本地没有该镜像，调 deploy/wps/build.sh"
    (cd ../deploy && ./wps/build.sh)
fi

echo "── 3/4 容器里跑 WPS ──"
docker run --rm --platform linux/amd64 \
    -v "$PWD/corpus:/in:ro" \
    -v "$PWD/out:/out" \
    -v "$PWD/docxfmt/wps.py:/opt/wps.py:ro" \
    -v "$PWD/docxfmt/wps_pages.py:/opt/wps_pages.py:ro" \
    -v "$PWD/docxfmt/wps_objects.py:/opt/wps_objects.py:ro" \
    -v "$PWD/docxfmt/wps_fields.py:/opt/wps_fields.py:ro" \
    -v "$PWD/docxfmt/wps_textbox.py:/opt/wps_textbox.py:ro" \
    -v "$PWD/docxfmt/wps_borders.py:/opt/wps_borders.py:ro" \
    "$IMAGE" \
    bash -lc "python3 /opt/wps.py --outdir /out --list /out/wps_paths.txt | tail -3 &&
              python3 /opt/wps_pages.py --outdir /out --list /out/wps_paths.txt | tail -2 &&
              python3 /opt/wps_objects.py --outdir /out --list /out/wps_paths.txt | tail -2 &&
              python3 /opt/wps_fields.py --outdir /out --list /out/wps_paths.txt | tail -2 &&
              python3 /opt/wps_textbox.py --outdir /out --list /out/wps_paths.txt | tail -2 &&
              python3 /opt/wps_borders.py --outdir /out --list /out/wps_paths.txt | tail -2"

echo "── 4/4 三方对账 ──"
uv run --quiet python -m docxfmt.compare --report
uv run --quiet python -m docxfmt.pages_compare
uv run --quiet python -m docxfmt.objects_compare
uv run --quiet python -m docxfmt.fields_compare
uv run --quiet python -m docxfmt.textbox_compare
uv run --quiet python -m docxfmt.style_compare
uv run --quiet python -m docxfmt.index_check
uv run --quiet python -m docxfmt.borders_compare
