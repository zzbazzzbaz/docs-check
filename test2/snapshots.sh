#!/bin/bash
# out/ 的对账快照 ↔ 压缩进版本管理
#
#   ./snapshots.sh pack      out/*.json → snapshots/*.json.gz（+ 报告与核验脚本）
#   ./snapshots.sh unpack    snapshots/*.json.gz → out/*.json
#
# 为什么压缩：自研侧 + WPS 侧共 49MB，gzip 后 2.2MB。out/ 本身仍不进版本（可重新生成）。
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-}" in
pack)
    mkdir -p snapshots/reports snapshots/tools
    for f in out/*.json; do
        gzip -9c "$f" > "snapshots/$(basename "$f").gz"
    done
    cp out/*.md snapshots/reports/ 2>/dev/null || true
    cp out/verify_*.txt snapshots/reports/ 2>/dev/null || true
    cp out/synth_*.py out/verify_*.py snapshots/tools/ 2>/dev/null || true
    echo "已打包 $(find snapshots -name '*.json.gz' | wc -l | tr -d ' ') 个快照，共 $(du -sh snapshots | cut -f1)"
    ;;
unpack)
    for f in snapshots/*.json.gz; do
        gunzip -c "$f" > "out/$(basename "${f%.gz}")"
    done
    echo "已还原 $(find out -name '*.json' | wc -l | tr -d ' ') 个快照到 out/"
    ;;
*)
    echo "用法: $0 pack|unpack"
    exit 1
    ;;
esac
