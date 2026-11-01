# DEV_ENV.md — 开发环境（uv 管理）

本仓库用 [uv](https://docs.astral.sh/uv/) 管理虚拟环境与依赖，替代 pip + venv。
**上游 `pyproject.toml` 不改**：下游依赖单独成清单，避免给上游提交制造永久冲突。

## 1. 一次性安装

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh      # 装到 ~/.local/bin/uv
source ~/.local/bin/env                              # 或重开 shell

cd /home/dafei/projects/TradingAgents
uv venv .venv --python 3.13                          # 建环境（会下载/选择 CPython 3.13）
uv pip install -e ".[dev]"                           # 上游依赖 + 开发依赖（pytest/ruff）
uv pip install -r requirements-downstream.txt        # 下游依赖（tushare）
uv pip install setuptools                            # 打包守卫测试需要
```

要与已验证的版本完全一致，装完后可对照 `requirements-lock.txt`：

```bash
uv pip install -r requirements-lock.txt
uv pip install -e . --no-deps
```

## 2. 日常命令

| 目的 | 命令 |
| --- | --- |
| 跑测试 | `uv run pytest -q` |
| 只跑下游测试 | `uv run pytest -q tests/downstream` |
| 真实数据冒烟 | `uv run pytest -q -m integration tests/downstream/test_tushare_live.py` |
| 代码风格 | `uv run ruff check .` |
| 临时加依赖（不改清单） | `uv pip install <pkg>` |
| 看当前环境 | `uv pip list` / `uv pip freeze` |

> `.venv` 里**没有 pip**（uv 有意如此）。要用 pip 语义请走 `uv pip ...`；
> `python -m pip` 会报 `No module named pip`。

## 3. 依赖分层

| 文件 | 内容 | 谁维护 |
| --- | --- | --- |
| `pyproject.toml` | 上游依赖 + `[dev]` 额外依赖 | **上游**，下游不改 |
| `requirements-downstream.txt` | 仅下游需要（`tushare`） | 下游 |
| `requirements-lock.txt` | 本机验证过的完整版本快照（不含可编辑的本地项目） | 下游，自动生成 |

## 4. 锁文件更新流程

```bash
# 改了下游依赖之后
uv pip install -r requirements-downstream.txt
uv run pytest -q                      # 必须全绿
uv pip freeze | grep -v '^-e ' | grep -v 'tradingagents @ file://' > requirements-lock.txt
# 手工恢复文件头注释（见现有文件前 4 行）
```

## 5. 从零重建（换机器 / 环境损坏）

```bash
rm -rf .venv
uv venv .venv --python 3.13
uv pip install -r requirements-lock.txt
uv pip install -e . --no-deps
uv run pytest -q
```

## 6. 迁移记录（2026-11-01）

| 项 | 值 |
| --- | --- |
| uv 版本 | 0.13.6 |
| 迁移前 | pip + venv，Python 3.13.12，99 个包 |
| 迁移后 | uv 管理，Python 3.13.18，按旧 freeze 做约束安装（版本未漂移） |
| 回退方案 | 迁移时保留 `.venv-pip-backup`，验证全绿后已删除；如需回退，按第 5 节重建即可 |
| 验证 | `pytest -q` → 1599 passed, 1 skipped；`ruff check .` → 全绿；`-m integration` → 9 passed |

## 7. 注意

- `uv venv` 可能选用与旧环境不同的补丁版本 Python（本次 3.13.12 → 3.13.18），
  上游要求 `>=3.11`，不构成风险；如需锁定解释器，可 `uv venv --python 3.13.12`。
- 缓存/结果目录仍在 `~/.tradingagents/`（上游默认），与 uv 无关。
- 不要在仓库里提交 `.venv*`；`.gitignore` 已覆盖。
