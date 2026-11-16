"""D-0060：OpenCode Go 端点需要会话头与自报家门的 User-Agent。

Go 订阅端点（https://opencode.ai/inference/go/openai/v1）按模型名直接路由，
但要求客户端：① 发送稳定的 `x-opencode-session`（路由与 prompt 缓存优化）；
② 用自己的 User-Agent 标识（如 tradingagents-web/1.0），而不是 SDK 默认名。
缺会话头会被 400 MissingSessionID 拒绝；把端点配错到 /inference/openai/v1
则按量计费（402）。见 https://opencode.ai/v2/docs/console/go/#where-can-i-use-it
"""

import uuid

from tradingagents.llm_clients.openai_client import OpenAIClient

GO_BASE = "https://opencode.ai/inference/go/openai/v1"


def test_go_endpoint_gets_session_and_user_agent_headers():
    client = OpenAIClient("deepseek-v4.1-flash", base_url=GO_BASE,
                          provider="openai_compatible")
    llm = client.get_llm()
    headers = llm.default_headers or {}
    assert headers.get("x-opencode-session"), "Go 端点缺会话头会被 400 拒绝"
    assert headers.get("User-Agent", "").startswith("tradingagents"), \
        "Go 要求客户端自报家门，不能留 SDK 默认 UA"


def test_session_id_is_stable_within_process():
    a = OpenAIClient("deepseek-v4.1-flash", base_url=GO_BASE,
                     provider="openai_compatible").get_llm()
    b = OpenAIClient("deepseek-v4.1-flash", base_url=GO_BASE,
                     provider="openai_compatible").get_llm()
    assert a.default_headers["x-opencode-session"] == b.default_headers["x-opencode-session"]
    # 且是个合法的 UUID（稳定、可追溯）
    uuid.UUID(a.default_headers["x-opencode-session"])


def test_non_go_endpoints_are_untouched():
    client = OpenAIClient("qwen-max", base_url="https://dashstage.example.com/v1",
                          provider="openai_compatible")
    llm = client.get_llm()
    assert not (llm.default_headers or {}).get("x-opencode-session"), \
        "非 Go 端点不应被注入 Go 专用头"
