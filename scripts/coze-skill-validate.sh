#!/usr/bin/env bash
# =============================================================================
# coze-skill-validate.sh — 校验 skill 目录可被扣子识别
#
# 检查项：
#   1. SKILL.md 存在且距包根为一级；frontmatter 含 name / description
#   2. scripts/**/*.py 语法正确（内存 compile，不生成 pyc）
#   3. 入口脚本冒烟：scripts/quotes.py --help 退出码为 0
#
# 前置：运行前需在仓库根执行 `python -m pip install -e .`（CI 已做），
#       使 quotes.py 可导入 tzt_api。
#
# 用法：bash scripts/coze-skill-validate.sh [skill_dir]（缺省 skill）
# =============================================================================
set -euo pipefail

SKILL_DIR="${1:-skill}"
QUOTES="$SKILL_DIR/scripts/quotes.py"

echo "==> [1/3] SKILL.md 结构"
[ -f "$SKILL_DIR/SKILL.md" ] || { echo "错误：$SKILL_DIR/SKILL.md 不存在" >&2; exit 1; }
for key in name description; do
  if ! awk -v k="$key" 'NR==1 && $0!="---"{exit} /^---/{c++;next} c==1&&$0~"^"k":"{found=1;exit} END{exit !found}' \
       "$SKILL_DIR/SKILL.md"; then
    echo "错误：SKILL.md frontmatter 缺少 $key" >&2
    exit 1
  fi
done
echo "OK  frontmatter(name/description) 完整"

echo "==> [2/3] 脚本语法"
if [ -d "$SKILL_DIR/scripts" ]; then
  while IFS= read -r -d '' f; do
    # 只在内存中编译，避免生成 __pycache__ 并污染后续压缩包。
    python -c 'import pathlib, sys; p = pathlib.Path(sys.argv[1]); compile(p.read_bytes(), str(p), "exec")' "$f"
  done < <(find "$SKILL_DIR/scripts" -name '*.py' -print0)
  echo "OK  脚本语法通过"
else
  echo "OK  无 scripts/ 目录（纯提示词 skill）"
fi

echo "==> [3/3] 入口冒烟（quotes.py --help 须 exit 0）"
[ -f "$QUOTES" ] || { echo "OK  无 scripts/quotes.py，跳过冒烟（如纯提示词 skill 属正常）" >&2; exit 0; }
python "$QUOTES" --help >/dev/null
echo "OK  quotes.py 可解析子命令"

echo "校验通过：$SKILL_DIR 可打包为扣子 skill。"
