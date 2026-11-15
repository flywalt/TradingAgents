"""D-0058：TRADINGAGENTS_HOME 环境变量优先于 ~/.tradingagents。

生产部署（vps-deploy 沙箱）要求全部运行时状态落在 /srv/<app>/data：
default_config 的三处默认路径（results/cache/memory）必须跟随单一开关。
"""

import importlib
from pathlib import Path


def test_tradingagents_home_env_overrides_default(monkeypatch, tmp_path):
    monkeypatch.setenv("TRADINGAGENTS_HOME", str(tmp_path))
    # 特异覆盖合法地优先于 home 开关；本测试要观察的是"默认值跟随 home"，先清掉它们
    for var in ("TRADINGAGENTS_RESULTS_DIR", "TRADINGAGENTS_CACHE_DIR",
                "TRADINGAGENTS_MEMORY_LOG_PATH", "TRADINGAGENTS_WEB_DB"):
        monkeypatch.delenv(var, raising=False)
    import tradingagents.default_config as dc

    cfg = importlib.reload(dc).build_default_config()

    assert cfg["results_dir"].startswith(str(tmp_path))
    assert cfg["data_cache_dir"].startswith(str(tmp_path))
    assert cfg["memory_log_path"].startswith(str(tmp_path))
    # 模块级 DEFAULT_CONFIG 与 build_default_config() 同源
    assert importlib.reload(dc).DEFAULT_CONFIG["results_dir"] == cfg["results_dir"]


def test_default_db_path_follows_home(monkeypatch, tmp_path):
    """D-0058：web 层 SQLite 兜底路径跟随 TRADINGAGENTS_HOME（沙箱内不许写 ~）。"""
    monkeypatch.setenv("TRADINGAGENTS_HOME", str(tmp_path))
    monkeypatch.delenv("TRADINGAGENTS_WEB_DB", raising=False)
    from tradingagents_web.app import default_db_path

    assert default_db_path() == Path(tmp_path) / "web" / "state.db"


def test_specific_dir_env_still_beats_home(monkeypatch, tmp_path):
    """特异目录变量优先于 TRADINGAGENTS_HOME（部署只用 home 开关时的兜底语义）。"""
    monkeypatch.setenv("TRADINGAGENTS_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TRADINGAGENTS_RESULTS_DIR", str(tmp_path / "specific"))
    monkeypatch.delenv("TRADINGAGENTS_CACHE_DIR", raising=False)
    import tradingagents.default_config as dc

    cfg = importlib.reload(dc).build_default_config()
    assert cfg["results_dir"] == str(tmp_path / "specific")
    assert cfg["data_cache_dir"].startswith(str(tmp_path / "home"))


def test_tradingagents_home_defaults_to_user_home(monkeypatch, tmp_path):
    monkeypatch.delenv("TRADINGAGENTS_HOME", raising=False)
    import tradingagents.default_config as dc

    home = importlib.reload(dc)._TRADINGAGENTS_HOME
    assert home.endswith(".tradingagents")
    assert str(tmp_path) not in home
