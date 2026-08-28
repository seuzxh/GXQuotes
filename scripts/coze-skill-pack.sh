#!/usr/bin/env bash
# =============================================================================
# coze-skill-pack.sh — 构建可独立运行的 Coze Skill 包
#
# 产物结构：
#   SKILL.md
#   references/
#   scripts/quotes.py
#   scripts/vendor/       tzt_api 及其第三方依赖
#
# 用法：
#   bash scripts/coze-skill-pack.sh <skill_dir> [output_dir] [skill_id] [version]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SKILL_DIR_ARG="${1:?需要 skill_dir（SKILL.md 所在目录）}"
OUTPUT_DIR_ARG="${2:-dist}"
SKILL_ID="${3:-}"
VERSION_ARG="${4:-}"

[ -d "$SKILL_DIR_ARG" ] || {
  echo "错误：skill 目录不存在：$SKILL_DIR_ARG" >&2
  exit 1
}
SKILL_DIR="$(cd "$SKILL_DIR_ARG" && pwd)"

# workflow_dispatch 只允许打包工作区内的目录，避免误把工作区外文件收入产物。
case "$SKILL_DIR/" in
  "$REPO_ROOT/"*) ;;
  *)
    echo "错误：skill_dir 必须位于仓库内：$REPO_ROOT" >&2
    exit 1
    ;;
esac

[ -f "$SKILL_DIR/SKILL.md" ] || {
  echo "错误：$SKILL_DIR 下未找到 SKILL.md" >&2
  exit 1
}

mkdir -p "$OUTPUT_DIR_ARG"
OUTPUT_DIR="$(cd "$OUTPUT_DIR_ARG" && pwd)"

# 从 SKILL.md frontmatter 提取简单标量。
_fm_get() { # usage: _fm_get <key>
  awk -v key="$1" '
    NR==1 && $0 != "---" { exit }
    /^---[[:space:]]*$/ { count++; next }
    count==1 && $0 ~ "^" key "[[:space:]]*:" {
      sub("^" key "[[:space:]]*:[[:space:]]*", "")
      gsub(/^["'"'"']|["'"'"']$/, "")
      print
      exit
    }
  ' "$SKILL_DIR/SKILL.md"
}

NAME="$(_fm_get name)"
if [ -z "$NAME" ]; then
  echo "警告：SKILL.md 缺少 name（用目录名代替）" >&2
  NAME="$(basename "$SKILL_DIR")"
fi

SKILL_ID="${SKILL_ID:-$(_fm_get skill_id)}"
SKILL_ID="${SKILL_ID:-$NAME}"
SKILL_ID="$(printf '%s' "$SKILL_ID" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/_/g')"
[ -n "$SKILL_ID" ] || SKILL_ID="skill"

if [ -n "$VERSION_ARG" ]; then
  VERSION="$VERSION_ARG"
else
  VERSION="$(_fm_get version)"
  if [ -z "$VERSION" ] && [ -f "$REPO_ROOT/pyproject.toml" ]; then
    VERSION="$(awk '
      /^\[project\][[:space:]]*$/ { in_project=1; next }
      /^\[/ { in_project=0 }
      in_project && /^[[:space:]]*version[[:space:]]*=/ {
        sub(/^[^=]*=[[:space:]]*/, "")
        gsub(/^["'"'"']|["'"'"'][[:space:]]*$/, "")
        print
        exit
      }
    ' "$REPO_ROOT/pyproject.toml")"
  fi
  VERSION="${VERSION:-0.0.0-dev}"
fi

if ! [[ "$VERSION" =~ ^[0-9A-Za-z][0-9A-Za-z._-]*$ ]]; then
  echo "错误：version 只能包含字母、数字、点、下划线和连字符：$VERSION" >&2
  exit 1
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
STAGE="$TMP/stage"
UNPACKED="$TMP/unpacked"
mkdir -p "$STAGE" "$UNPACKED"

# 复制 skill 源文件。所有清理仅发生在临时目录中。
cp -R "$SKILL_DIR/." "$STAGE/"
find "$STAGE" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$STAGE" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '.DS_Store' \) -delete

# 将本仓 tzt_api 及已安装的 requests/PyYAML 运行时依赖复制进包内。
# workflow 在上一步已经 pip install -e .；这里不再次联网或执行构建后端。
mkdir -p "$STAGE/scripts/vendor"
python - "$STAGE/scripts/vendor" "$REPO_ROOT" <<'PY'
import importlib.util
import pathlib
import shutil
import sys

vendor = pathlib.Path(sys.argv[1])
repo_root = pathlib.Path(sys.argv[2])

for module_name in ("requests", "urllib3", "certifi", "charset_normalizer", "idna", "yaml"):
    spec = importlib.util.find_spec(module_name)
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit(f"缺少打包依赖：{module_name}；请先执行 python -m pip install -e .")
    source = pathlib.Path(next(iter(spec.submodule_search_locations)))
    shutil.copytree(source, vendor / module_name, dirs_exist_ok=True)

shutil.copytree(
    repo_root / "tzt_api",
    vendor / "tzt_api",
    dirs_exist_ok=True,
    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
)
PY

find "$STAGE/scripts/vendor" -type d -name '__pycache__' -prune -exec rm -rf {} +
# requests/PyYAML 的依赖均有纯 Python 实现；移除本机构建的可选扩展，避免产物绑定
# runner 的 Python 小版本、操作系统或 CPU 架构。
find "$STAGE/scripts/vendor" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '*.so' -o -name '*.pyd' \) -delete

ARTIFACT="$OUTPUT_DIR/${SKILL_ID}-v${VERSION}.skill"
BUILT_ARCHIVE="$TMP/built.skill"
(
  cd "$STAGE"
  zip -q -r -X "$BUILT_ARCHIVE" . \
    -x '*.DS_Store' '*/__pycache__/*' '*.pyc' '*.pyo' '*.so' '*.pyd'
)
mv "$BUILT_ARCHIVE" "$ARTIFACT"

unzip -Z1 "$ARTIFACT" > "$TMP/archive-entries.txt"
if ! grep -Fxq 'SKILL.md' "$TMP/archive-entries.txt"; then
  echo "错误：包根目录缺少 SKILL.md" >&2
  exit 1
fi
if ! grep -Fxq 'config/kline_config.yaml' "$TMP/archive-entries.txt"; then
  echo "错误：包根目录缺少内部行情配置" >&2
  exit 1
fi

# 用一个不继承仓库依赖的全新 venv 验证 Release 包确实可独立导入并启动。
unzip -q "$ARTIFACT" -d "$UNPACKED"

# 发布文档和用户可见帮助不得泄漏源码仓库布局或具体网关地址。Skill 可能安装在
# 任意目录，运行入口必须相对已加载的 SKILL.md 定位；具体地址仅保留在内部配置中。
if grep -nE 'skill/scripts/quotes\.py|tzt_api/config/kline_config\.yaml' \
  "$UNPACKED/SKILL.md" "$UNPACKED/scripts/quotes.py"; then
  echo "错误：发布物仍包含源码仓库专用路径" >&2
  exit 1
fi
if grep -nE 'https?://([0-9]{1,3}\.){3}[0-9]{1,3}(:[0-9]+)?' \
  "$UNPACKED/SKILL.md" "$UNPACKED/scripts/quotes.py"; then
  echo "错误：发布物的用户可见说明仍包含具体网关地址" >&2
  exit 1
fi

python -m venv "$TMP/smoke-venv"
"$TMP/smoke-venv/bin/python" -I "$UNPACKED/scripts/quotes.py" --help >/dev/null

echo "已生成：$ARTIFACT"
echo "skill_id=$SKILL_ID version=$VERSION"
echo "隔离冒烟通过：scripts/quotes.py --help"
