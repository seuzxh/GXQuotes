# Coze Skill 自动打包与发布

本仓库通过 GitHub Actions 校验 `skill/`，构建自包含的 `.skill`（ZIP）并上传为
workflow artifact。推送 `v*` tag 时，Actions 还会自动创建 GitHub Release，并把
`.skill` 附到 Release。

Release 包以 Coze 使用的 Python 3.11 为目标运行时；仓库中的 tzt-api 库本身仍支持
Python ≥3.9。

产物包含：

- 包根目录的 `SKILL.md`、`references/` 和 `scripts/`；
- `scripts/vendor/` 中的 `tzt_api`、`requests`、`PyYAML` 等全部 Python 依赖；
- 不包含 `__pycache__`、`.pyc`、本地虚拟环境或仓库源码树。

可选的本机二进制扩展也会被剔除，依赖使用纯 Python 实现，避免产物绑定 GitHub runner
的操作系统、CPU 架构或 Python 小版本。

打包完成前，流水线会将产物解压到临时目录，并在一个全新虚拟环境中执行
`scripts/quotes.py --help`。这可以避免“仓库里能运行、Release 包缺依赖”的假通过。

## GitHub 仓库需要怎样配置

### 1. 启用 Actions

进入仓库：

`Settings → Actions → General`

- `Actions permissions`：允许使用 GitHub Actions。最简单的是选择
  **Allow all actions and reusable workflows**。
- 如果组织只允许白名单 Action，需要允许：
  `actions/checkout`、`actions/setup-python`、`actions/upload-artifact`、
  `actions/download-artifact`、`softprops/action-gh-release`。
- `Workflow permissions` 建议保留 **Read repository contents and packages permissions**。
  workflow 默认只读，只在 tag 对应的 `release` job 中显式申请
  `contents: write`。不需要开启 “Allow GitHub Actions to create and approve pull requests”。

如果组织或 Enterprise 策略禁止 workflow 申请 `contents: write`，需要让组织管理员为
本仓库放开 Release 写权限，否则构建 artifact 会成功，但创建 Release 会收到 403。

### 2. 不需要配置 GitHub Secrets

构建过程不访问真实行情接口，只执行 `--help` 冒烟，因此 GitHub 仓库不需要配置
`KLINE_API_BASE_URL`，也不需要 Coze token。

Release Skill 包携带运行时默认配置，构建过程不会请求该网关。管理员如需切换部署环境，
可在运行平台设置 `KLINE_API_BASE_URL` 或 `KLINE_CONFIG_PATH` 覆盖包内配置。

### 3. 可选：把 PR 校验设为必需检查

workflow 已监听 `pull_request`。如果希望相关改动必须通过打包验证才能合并，可进入：

`Settings → Branches → master 的保护规则 → Require status checks`

选择检查：`coze-skill-pack / Validate and build`。

## 如何发布

确保目标提交已经推送，然后创建并推送以 `v` 开头的 tag：

```bash
git tag -a v2.0.1 -m "Release v2.0.1"
git push origin v2.0.1
```

Actions 将依次执行：

1. 校验 `SKILL.md`、Python 语法和 CLI；
2. 从 tag 得到版本 `2.0.1`；
3. 构建 `gxquotes-v2.0.1.skill`；
4. 在干净 venv 中验证压缩包可以独立启动；
5. 上传 workflow artifact；
6. 创建 `v2.0.1` Release，并附加 `.skill`。

可在以下位置检查结果：

- `Actions → coze-skill-pack`：查看每一步日志和临时 artifact；
- `Releases → v2.0.1`：下载正式 `.skill`。

如果 tag 已推送但构建失败，修复后可以在该 workflow run 页面选择 **Re-run jobs**。
不要为了重跑而重复创建同名 tag。若 tag 指向了错误提交，应优先发布一个新版本 tag；
只有尚未对外使用时才考虑删除并重建 tag。

## 手动构建但不发布 Release

进入：

`Actions → coze-skill-pack → Run workflow`

可填写：

- `skill_dir`：默认 `skill`，必须位于本仓库内；
- `skill_id`：默认读取 `SKILL.md` 的 `name`；
- `version`：默认读取 `pyproject.toml` 的项目版本。

手动运行只生成 workflow artifact，不创建 Release。只有推送 `v*` tag 才会发布 Release。

## 上传到扣子后仍需配置什么

从 GitHub Release 下载 `.skill`，在扣子编程中选择“上传技能包”。依赖和内部默认网关
配置均已包含在包内，普通使用无需再次设置。管理员需要覆盖默认部署时，可在运行平台设置：

```text
KLINE_API_BASE_URL=https://替代网关地址
```

覆盖地址必须能从运行平台访问。不要在 `SKILL.md`、命令示例、聊天回答或错误信息中
展示具体网关；若网关需要 API Key，应使用运行平台的凭证变量。

## 本地复现 Actions 打包

首次准备环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e . pytest
```

校验并打包：

```bash
PATH="$PWD/.venv/bin:$PATH" bash scripts/coze-skill-validate.sh skill
PATH="$PWD/.venv/bin:$PATH" bash scripts/coze-skill-pack.sh skill dist gxquotes 2.0.1
unzip -l dist/gxquotes-v2.0.1.skill
```

首次安装项目依赖时需要访问 Python 包索引；打包脚本本身会复制当前虚拟环境中已安装的
运行时依赖，不会再次联网或执行项目构建后端。
