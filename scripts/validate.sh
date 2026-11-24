#!/bin/bash
# kb-plugin 的统一检查入口（插件开发规范 C2）：CI、Codex 审查和 autopilot 都调用它。
#   bash scripts/validate.sh          全量：清单检查、本机路径检查、全部单元测试
#   bash scripts/validate.sh --quick  快档：只跑清单检查与本机路径检查（几秒）
# 只检查本仓库内容，不读取任何 kb 知识库。保持 bash 3.2 兼容（macOS 自带）。
set -eu

cd "$(dirname "$0")/.."

quick=0
case "${1:-}" in
  '') ;;
  --quick) quick=1 ;;
  *) echo "用法：bash scripts/validate.sh [--quick]" >&2; exit 2 ;;
esac

echo "== 清单检查"
python3 -B scripts/check-manifests.py
echo "== 本机路径检查"
python3 -B scripts/check_local_paths.py

if [ "$quick" -eq 1 ]; then
  echo "快档完成（未跑单元测试）"
  exit 0
fi

echo "== 单元测试"
python3 -m unittest discover -s tests
echo "全部检查通过"
