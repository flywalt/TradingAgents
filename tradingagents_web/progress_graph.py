"""The run drawn as a graph: topology and both layouts, computed in Python.

Layout lives here rather than in the browser so it can be tested: nodes must not
overlap, must stay inside the canvas, and every edge must join two nodes that
exist. ``static/run-page.js`` only paints this and lights it from the recorded
events.

Two layouts exist because the shape does not survive a 360px column: wide puts
the analysts in one row, narrow stacks the spine and keeps only the two debate
pairs side by side.
"""

from __future__ import annotations

from .labels import ANALYST_NODES, NODE_LABELS

#: The order analysts are drawn in, regardless of the order a run submitted them.
ANALYST_ORDER = ("market", "social", "news", "fundamentals")

#: Short words for the narrow layout, where a 78px box holds four characters.
_SHORT = {
    "Market Analyst": "市场", "Sentiment Analyst": "情绪",
    "News Analyst": "新闻", "Fundamentals Analyst": "基本面",
    "Memory Log": "记忆", "Bull Researcher": "多头", "Bear Researcher": "空头",
    "Aggressive Analyst": "激进", "Conservative Analyst": "保守",
    "Neutral Analyst": "中性",
}

#: Nodes that exist whether or not an analyst was selected.
_CORE = (
    ("bull", "Bull Researcher"),
    ("bear", "Bear Researcher"),
    ("research-manager", "Research Manager"),
    ("trader", "Trader"),
    ("risk-aggressive", "Aggressive Analyst"),
    ("risk-conservative", "Conservative Analyst"),
    ("risk-neutral", "Neutral Analyst"),
    ("memory", "Memory Log"),
    ("portfolio", "Portfolio Manager"),
)

_WIDE = {
    "viewBox": "0 0 960 640",
    "height": 48,
    "analyst_y": 48,
    "analyst_width": 150,
    "analyst_x": {"market": 40, "social": 216, "news": 392, "fundamentals": 568},
    "default_width": 150,
    "boxes": {
        "memory": (760, 48),
        "bull": (280, 168),
        "bear": (530, 168),
        "research-manager": (405, 272),
        "trader": (405, 368),
        "risk-aggressive": (150, 464),
        "risk-conservative": (405, 464),
        "risk-neutral": (660, 464),
        "portfolio": (405, 560),
    },
    "bypass_x": 944,
    "cycle_drop": 36,
}

_NARROW = {
    "viewBox": "0 0 360 520",
    "height": 40,
    "analyst_y": 20,
    "analyst_width": 78,
    "analyst_x": {"market": 12, "social": 99, "news": 186, "fundamentals": 273},
    "default_width": 200,
    "boxes": {
        "memory": (80, 392),
        "bull": (20, 100),
        "bear": (190, 100),
        "research-manager": (80, 176),
        "trader": (80, 248),
        "risk-aggressive": (20, 320),
        "risk-conservative": (130, 320),
        "risk-neutral": (240, 320),
        "portfolio": (80, 464),
    },
    "widths": {"bull": 150, "bear": 150,
               "risk-aggressive": 100, "risk-conservative": 100, "risk-neutral": 100},
    "bypass_x": 8,
    "cycle_drop": 16,
}


def _n(value: float) -> str:
    return f"{value:g}"


def _build_nodes(spec: dict, analysts: list[str]) -> list[dict]:
    nodes = []
    for key in ANALYST_ORDER:
        if key not in analysts:
            continue
        kernel = ANALYST_NODES[key]
        x = spec["analyst_x"][key]
        nodes.append(_node(f"analyst-{key}", kernel, x, spec["analyst_y"],
                           spec["analyst_width"], spec["height"]))
    for node_id, kernel in _CORE:
        x, y = spec["boxes"][node_id]
        width = spec.get("widths", {}).get(node_id, spec["default_width"])
        nodes.append(_node(node_id, kernel, x, y, width, spec["height"]))
    return nodes


def _node(node_id: str, kernel: str, x: int, y: int, width: int, height: int) -> dict:
    label = NODE_LABELS[kernel]
    return {"id": node_id, "kernel": kernel, "label": label,
            "short": _SHORT.get(kernel, label),
            "x": x, "y": y, "w": width, "h": height}


def _centre_x(node: dict) -> float:
    return node["x"] + node["w"] / 2


def _drop(src: dict, dst: dict, to_x: float | None = None) -> str:
    """Down out of ``src``, across, and down into ``dst``."""
    x1 = _centre_x(src)
    x2 = _centre_x(dst) if to_x is None else to_x
    y1 = src["y"] + src["h"]
    mid = (y1 + dst["y"]) / 2
    return (f"M {_n(x1)} {_n(y1)} V {_n(mid)} H {_n(x2)} V {_n(dst['y'])}")


def _across(src: dict, dst: dict) -> str:
    """Straight across the row: the debate hand-off."""
    y = src["y"] + src["h"] / 2
    return f"M {_n(src['x'] + src['w'])} {_n(y)} H {_n(dst['x'])}"


def _return_arc(src: dict, dst: dict, drop: int) -> str:
    """Back under the row: the debate loop closing."""
    y = src["y"] + src["h"] + drop
    return (f"M {_n(_centre_x(src))} {_n(src['y'] + src['h'])} V {_n(y)} "
            f"H {_n(_centre_x(dst))} V {_n(dst['y'] + dst['h'])}")


def _bypass(src: dict, dst: dict, margin: int) -> str:
    """Out to the margin and down: the memory log only reaches the portfolio."""
    if margin < src["x"]:
        x1, x2 = src["x"], dst["x"]
    else:
        x1, x2 = src["x"] + src["w"], dst["x"] + dst["w"]
    y1 = src["y"] + src["h"] / 2
    y2 = dst["y"] + dst["h"] / 2
    return f"M {_n(x1)} {_n(y1)} H {_n(margin)} V {_n(y2)} H {_n(x2)}"


def _edges(nodes: dict[str, dict], spec: dict) -> list[dict]:
    edges = []
    analysts = [node_id for node_id in nodes if node_id.startswith("analyst-")]
    bull = nodes["bull"]
    # Fan the analysts into the bull's top edge so their lines stay distinguishable.
    for index, node_id in enumerate(analysts, start=1):
        target = bull["x"] + bull["w"] * index / (len(analysts) + 1)
        edges.append(_edge(node_id, "bull", "flow", _drop(nodes[node_id], bull, target)))
    edges.append(_edge("bull", "bear", "debate", _across(bull, nodes["bear"])))
    for source, target in (("bull", "research-manager"), ("bear", "research-manager")):
        manager = nodes["research-manager"]
        offset = 1 if source == "bull" else 2
        to_x = manager["x"] + manager["w"] * offset / 3
        edges.append(_edge(source, target, "flow", _drop(nodes[source], manager, to_x)))
    edges.append(_edge("research-manager", "trader", "flow",
                       _drop(nodes["research-manager"], nodes["trader"])))
    edges.append(_edge("trader", "risk-aggressive", "flow",
                       _drop(nodes["trader"], nodes["risk-aggressive"])))
    edges.append(_edge("risk-aggressive", "risk-conservative", "debate",
                       _across(nodes["risk-aggressive"], nodes["risk-conservative"])))
    edges.append(_edge("risk-conservative", "risk-neutral", "debate",
                       _across(nodes["risk-conservative"], nodes["risk-neutral"])))
    edges.append(_edge("risk-neutral", "risk-aggressive", "debate",
                       _return_arc(nodes["risk-neutral"], nodes["risk-aggressive"],
                                   spec["cycle_drop"])))
    edges.append(_edge("risk-neutral", "portfolio", "flow",
                       _drop(nodes["risk-neutral"], nodes["portfolio"])))
    edges.append(_edge("memory", "portfolio", "bypass",
                       _bypass(nodes["memory"], nodes["portfolio"], spec["bypass_x"])))
    return edges


def _edge(source: str, target: str, kind: str, path: str) -> dict:
    return {"from": source, "to": target, "kind": kind, "d": path}


def _layout(spec: dict, analysts: list[str]) -> dict:
    nodes = _build_nodes(spec, analysts)
    by_id = {node["id"]: node for node in nodes}
    return {"viewBox": spec["viewBox"], "nodes": nodes, "edges": _edges(by_id, spec)}


def topology(analysts: list[str] | None) -> dict:
    """Both layouts for the analysts this run selected."""
    selected = [key for key in ANALYST_ORDER if key in set(analysts or ())]
    return {"wide": _layout(_WIDE, selected), "narrow": _layout(_NARROW, selected)}
