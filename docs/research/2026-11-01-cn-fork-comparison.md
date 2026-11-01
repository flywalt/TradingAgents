# TradingAgents-CN vs upstream TradingAgents — fork comparison

- Upstream inspected: `TauricResearch/TradingAgents` @ `main`, CHANGELOG `[0.7.1] — 2026-10-27`, 23 dirs / 213 files.
- Fork inspected: `hsliuping/TradingAgents-CN` @ default branch `v3.0`, `VERSION` = `3.0.0`, `BUILD_INFO` = `3.0.0-beta.4` (build 2026-08-16), 242 dirs / 1639 files.
- Method: read-only inspection of the two repos (no clone, no execution). Paths below are repo-relative; `CN:` / `UP:` prefixes name the repo.

## Verdict

The CN fork is a **product, not a library**: a self-hosted multi-user research platform (FastAPI + Vue 3 + MongoDB + Redis + worker) that vendors an *old* copy of the upstream Python package as its analysis kernel, while upstream remains a single-user, CLI-driven analysis library with a clean vendor-routing data layer. CN adds the whole application layer — auth, portfolios, paper trading, screening, knowledge base, skills, licensing — with ~8× the file count (1639 vs 213). The two have stopped co-evolving: CN's default branch is one squashed snapshot commit (`2026-09-22`, "TradingAgents-CN v3.0.0 社区版首发"), its legacy `main` ends `2026-07-24`, and it carries no upstream ancestry. The useful signal is narrow: CN is the only place I found real A-share cost-basis bookkeeping (qfq cost vs unadjusted fill), a cheap plausibility check on user-entered cost prices, and a config-driven vendor-priority adapter layer — all fitting our "adapter + config, patch upstream minimally" rule. The rest (web stack, licensing, Pro/community stripping) is product surface we should not absorb.

## Differences

Legend: **D** = fork differs from a concept upstream also has; **A** = upstream lacks the concept entirely.

| Dimension | Upstream | CN fork | Evidence path |
|---|---|---|---|
| Shape (**A**) | CLI + library only: `cli/`, `tradingagents/` | Web product: FastAPI (`app/main.py`, 58 routers in `app/routers/`), Vue 3 (`frontend/src`), worker on :8001 (`app/worker/worker_app.py`) | `UP: cli/`, `tradingagents/`; `CN: app/`, `frontend/src`, `app/worker/worker_app.py` |
| Package layout (**D**) | `tradingagents/` with `agents/`, `dataflows/vendors/`, `graph/`, `llm_clients/`, `memory/`, `portfolio.py`, `backtest.py` | Old-style `tradingagents/` (`agents/utils/agent_utils.py`, `llm_adapters/`, no `memory/`, no `llm_clients/`) **plus** new top-level `app/`, `core/`, `frontend/`, `skills/` | `CN: tradingagents/graph/setup.py` (imports `from tradingagents.agents import *`, `ChatOpenAI`, `bull_memory`) vs `UP: tradingagents/graph/setup.py` (typed `create_*` factories) |
| Packaging (**D**) | `pip install -e ".[dev]"` in CI | `pyproject.toml` ships only `include = ["tradingagents*"]` — `app/`/`core/` are not packaged; runs from checkout | `CN: pyproject.toml`; `UP: .github/workflows/ci.yml` |
| Auth / multi-user (**A**) | none | JWT login/refresh, per-`user_id` documents | `CN: app/routers/auth_db.py` (`LoginResponse.access_token`, `RefreshTokenRequest`), `app/models/user.py` |
| Storage (**A**) | CSV files under `~/.tradingagents`, optional LangGraph checkpoint | MongoDB + Redis mandatory for startup | `CN: app/core/database.py`, `app/core/redis_client.py`, README "MongoDB 7.0+ … 与 Redis 6+" |
| Vendor model (**D**) | Explicit chain per category; "requests are NOT silently routed to vendors you didn't choose" | Numeric priority per adapter loaded from DB config, `.env` can force-disable, DB-first `local` adapter wins by default | `UP: tradingagents/default_config.py` (`data_vendors`), `dataflows/router.py` (`VENDOR_METHODS`); `CN: app/services/data_sources/manager.py`, `base.py` |
| Adapter priorities (**D**) | n/a (category string chain) | `local=10 > tushare=3 > akshare=2 / qmt=2 > baostock=1` | `CN: app/services/data_sources/{local,tushare,akshare,qmt,baostock}_adapter.py` |
| Caching (**D**) | one CSV-per-symbol cache, 900 s TTL, 10-day stale guard | 7 cache modules (file, Mongo+Redis db, adaptive, integrated, app adapter) | `UP: dataflows/vendors/yahoo/ohlcv.py` (`OHLCV_CACHE_TTL_SECONDS`, `MAX_OHLCV_STALE_DAYS`); `CN: tradingagents/dataflows/cache/` |
| Rate limiting (**D**) | retry/backoff + typed errors, no shared quota limiter | ASGI-level sliding-window limiter + per-provider call budgets noted in code | `UP: dataflows/net.py`, `vendors/yahoo/common.py` (`yf_retry`); `CN: app/core/rate_limiter.py`, `app/services/data_sources/tushare_adapter.py` |
| Adjustment 复权 (**A**) | none — always `auto_adjust=True, actions=False`; `Position.average_price` is one number | `adj: None|"qfq"|"hfq"`, default qfq in the Tushare path; positions hold **two** cost bases | `UP: dataflows/vendors/yahoo/ohlcv.py`, `tradingagents/portfolio.py`; `CN: app/services/data_sources/base.py`, `providers/china/tushare.py` (`adj='qfq'` "与同花顺一致"), `app/models/portfolio.py` |
| Cost-basis bookkeeping (**A**) | `average_price` only | `cost_price`(前复权, P&L) + `original_cost_price`(不复权实际成交价) + `original_avg_cost` + `price_adjust_type`, with unadjusted→qfq conversion via `adj_factor` and a 2% tolerance check against buy-date high/low | `CN: app/models/portfolio.py`, `app/services/portfolio_service.py` (`tolerance = 0.02`, `_validate_cost_price_against_historical`) |
| Indicators (**D**) | `stockstats` + `best_ind_params` descriptions + bulk date-keyed window | `stockstats` + old single-value window, offline CSV with hard-coded `2015-01-01-2025-03-25` name | `UP: dataflows/vendors/yahoo/market.py`; `CN: tradingagents/dataflows/technical/stockstats.py` |
| Analysts/topology (**D**) | market, news, fundamentals, sentiment; bull/bear; 3 risk debators; RM/PM | Same skeleton plus `china_market_analyst.py`, `index_analyst.py`, `sector_analyst.py`; second engine in `core/agents/` (planner/registry/quality gate) | `UP: tradingagents/agents/analysts/`; `CN: tradingagents/agents/analysts/`, `core/agents/{planner.py,analyst_registry.py}` |
| Prompt storage (**D**) | inline in agent modules, English, `get_language_instruction` | inline + `core/prompts/` file loader (`prompts/{zh,en}/…`) that has no matching files in-repo; DB prompt templates and injection policy | `CN: core/prompts/loader.py`, `prompts/` (only `email_templates`), `app/models/prompt_injection_policy.py` |
| Market rules (**A**) | none | T+1 available-qty from Mongo `paper_market_rules.t_plus`; per-market fee model; lot size / 涨跌停 only as knowledge text and breadth statistics | `CN: app/routers/paper.py` (`_get_available_quantity`, `_get_market_rules`), `core/knowledge/knowledge_data.py` (`concept_limit_up_down`, `concept_a_share_lot_size`), `core/tools/index_tools.py` |
| Trading calendar (**D**) | no calendar concept; date-window helpers only | `trade_cal` (SSE) inside the Tushare adapter for "latest trading day"; paper trading compares against `datetime.utcnow().date()` instead | `CN: app/services/data_sources/tushare_adapter.py`, `app/routers/paper.py`; `UP: dataflows/date_window.py` |
| Tests/CI (**D**) | 100+ focused tests, `ci.yml` matrix 3.11–3.14 + NY-timezone run + clean-install smoke, release workflow | Big `tests/` tree (unit/integration/e2e/acceptance/system) **plus** dozens of `debug_*.py`/`quick_*.py` scripts at `tests/` root; `pytest.ini` masks failures via `-k "not (test_server_config or test_stock_codes)"`; no `.github/workflows` at all | `UP: .github/workflows/ci.yml`, `tests/`; `CN: tests/`, `pytest.ini`, `.github/` (only ISSUE_TEMPLATE + pull_request_template) |
| Deps / release (**D**) | semver CHANGELOG, `release-assets.yml` | semver CHANGELOG + `cliff.toml` + `BUILD_INFO` + `publish_community.py` snapshot pipeline; deps are all `>=` bounds, no lockfile for Python | `CN: pyproject.toml`, `CHANGELOG.md`, `BUILD_INFO`; `UP: CHANGELOG.md`, `pyproject.toml` |
| Licence (**A**) | Apache-2.0 | "hybrid-licensed (Apache-2.0 core + proprietary source-available application layer)", community/Pro split, CLA | `CN: README.md`, `LICENSE`, `CLA.md` |
| Maintenance (**D**) | active: commits through `2026-10-27` | default branch `v3.0` = **one** commit `51060a7`, `2026-09-22`; legacy `main` last commit `2026-07-24` | `commits.atom` for both repos |

## Reference-worthy for us (value / effort)

1. **Dual cost basis with explicit 复权 semantics** (high value / medium effort). `CN: app/models/portfolio.py` + `portfolio_service.py`. Keep P&L math on one declared basis and store the actual fill separately; convert with `adj_factor`, never mix bases. This is the single idea worth porting, and it maps cleanly onto our `docs/TUSHARE.md` 复权 constraint.
2. **Cost-price plausibility check** (medium / low). Validate a user-entered cost against the buy-date `[low, high]` with a tolerance (they use 2% to absorb fees) and reject nonsense. Pure function, no infra.
3. **`adj` as a plumbed parameter with a declared default** (high / low-medium). `CN: app/services/data_sources/base.py` (`adj: None|"qfq"|"hfq"`), `akshare_adapter.py` (`adjust_map`), `tushare_adapter.py`. Cheap to add to our adapter contract; prevents silent cross-basis comparisons.
4. **Config-driven vendor priority with fallback loop + attempt timing logs** (high / medium). `CN: manager.py` `get_*_with_fallback`, `app/core/data_source_priority.py`. Our upstream `VENDOR_METHODS` is a static chain; a priority table lets A-share vendors be ranked per data category.
5. **Per-market fee/settlement config table** (medium / low). `CN: app/routers/paper.py`: stamp duty, transfer fee, SEC fee in one `paper_market_rules` doc — a good shape for A-share 印花税/过户费/佣金 without hardcoding.
6. **T+1 available quantity derived from today's buys** (medium / medium). `CN: paper.py` `_get_available_quantity`. The idea is right; their UTC-date implementation is not (see below).
7. **Market-rules text blocks injected into prompts** (medium / low). `CN: core/knowledge/knowledge_data.py` (涨跌停 10/20/30%, 5% ST, 100-share lots). Complements hard rules with rationale the LLM can cite.
8. **Sliding-window rate limiter** (low-medium / low). `CN: app/core/rate_limiter.py` — deque + `asyncio.Lock`, reusable for Tushare call budgets.
9. **Data-source consistency checker** (medium / high). `CN: app/services/data_consistency_checker.py`. Valuable, but only once we run two real A-share sources.

## Do not copy

1. **Single-squashed-snapshot release process.** `v3.0` has one commit and no upstream ancestry, so `git rebase upstream/main` is impossible and drift is unmeasurable. Directly violates our `docs/UPSTREAM_SYNC.md` model.
2. **God-module style.** `portfolio_service.py` 287 KB, `config_service.py` 269 KB, `data_source_manager.py` 136 KB, `app/routers/config.py` 131 KB, `app/main.py` 58 KB. Unreviewable, untestable, and it is where their state bugs will live.
3. **Licence/code-stripping split (community vs Pro).** `app/router_registry.py` admits a single unregistered Pro route "即泄露". Shipping one repo that is post-processed into two products is a compliance and CI trap for us.
4. **`pytest.ini` that excludes tests by name** (`-k "not (test_server_config or test_stock_codes)"`) plus hundreds of `debug_*.py` at `tests/` root, with no CI. Their test tree says less than its size implies.
5. **Unpinned Python deps** (`pyproject.toml` is all `>=`, `requirements.txt` marked "已弃用"). Our `docs/UPSTREAM_DELTA.md` needs reproducible installs for rebase verification.

## Unverified / uncertain

- Nothing was executed: no install, no DB, no test run. All statements are static reading.
- **Scheduler backend**: `apscheduler` is declared in `pyproject.toml` and `app/routers/scheduler.py` exists (57 KB), but that router contains no `apscheduler` reference; I did not trace where the job store lives. README also lists 定时分析/批量分析 as **Pro-only**, which contradicts the presence of a community router — unresolved.
- **Runtime vendor order**: priorities are overridden from Mongo (`UnifiedConfigManager`), so the static defaults above may not match a running instance.
- **Amount of verbatim upstream code** in `tradingagents/`: not measurable via diff because of the snapshot commit. Structure and imports suggest a 2024/2025-era upstream, not 0.7.x.
- `core/{assistant,workflow,backtest,embedded_nanobot}` and `skills/` were only sampled; whether backtest/agent-workshop ship in the community build is unconfirmed beyond README's feature table.
- QMT/通达信 adapters not verified as functional (their own comments note QMT must be running; news falls back to AKShare).
- `LICENSE`/`CLA.md` not audited line by line; "hybrid" is quoted from README only.
- `tests/` listing was truncated by tooling, so its file counts are approximate.

## 对路线的直接含义（本仓库视角，2026-11-01）

1. **数据层方向无需改**：CN 的"优先级 + 回退"并没有超出我们已有的有序 vendor 链 + typed error；
   唯一可借的是"尝试耗时日志"，属于可观测性，不是架构。
2. **组合/成本价是下一步唯一值得优先借的东西**：等我们做交易可行性或持仓分析时，
   按"qfq 成本价 + 不复权真实成交价"双存，并用 `adj_factor` 换算，别混口径。
3. **不要因为 CN 有 UI/多用户/权限就去补产品层**：那 8 倍文件量是产品，不是研究能力；
   我们的路线仍是"数据层 → agent/prompt → 组合与风控"。
4. **CN 的 T+1 实现是反面教材**：它用 `datetime.utcnow().date()` 而不是交易日历；
   我们的 `trading_cn/calendar.py` + `trading_rules.settlement_date()` 已经是对的，接 agent 时直接用。
5. **涨跌停/整手/ST 在 CN 里只是知识库文本**：说明"把规则算出来"这件事我们做得比它扎实，
   不必回头怀疑之前的 `trading_rules.py`。
