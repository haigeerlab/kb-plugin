#!/bin/bash
# kb-plugin 的统一检查入口（插件开发规范 C2）：CI、Codex 审查和 autopilot 都调用它。
#   bash scripts/validate.sh          全量：清单检查、本机路径检查、全部单元测试，最后列出最慢的测试文件
#   bash scripts/validate.sh --quick  快检查：清单与本机路径检查，加上本分支改动涉及的测试；
#                                     改动对应不上测试时退回全量（规则见 scripts/select_tests.py）
# 会话日常做 task 跑 --quick，全量留给合并前和 CI。
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

tests=ALL
if [ "$quick" -eq 1 ]; then
  echo "== 挑选改动涉及的测试"
  tests="$(python3 -B scripts/select_tests.py)"
fi

if [ "$tests" != ALL ]; then
  if [ -z "$tests" ]; then
    echo "快检查完成（改动不涉及单元测试）"
    exit 0
  fi
  echo "== 单元测试（快检查）：$tests"
  cd tests
  printf '%s\n' "$tests" | xargs python3 -m unittest
  echo "快检查通过"
  exit 0
fi

echo "== 单元测试（全量，逐个文件）"
timings="$(mktemp "${TMPDIR:-/tmp}/kb-validate-XXXXXX")"
trap 'rm -f "$timings"' EXIT
for file in tests/test_*.py; do
  name="$(basename "$file")"
  start=$(date +%s)
  python3 -m unittest discover -s tests -p "$name"
  echo "$(( $(date +%s) - start )) $name" >> "$timings"
done
echo "== 最慢的测试文件（秒）"
sort -rn "$timings" | head -5
echo "全部检查通过"
