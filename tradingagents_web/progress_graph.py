"""The run drawn as a graph: topology, groups and both layouts, in Python.

Layout lives here rather than in the browser so it can be tested: nodes must not
overlap, must stay inside the canvas and inside their group, and every edge must
join two nodes that exist through fixed ports. ``static/run-page.js`` only
paints this and lights it from the recorded events.

Drawing grammar (what the viewer can rely on):

- one vertical spine per layout; every stage's boxes share a row and a baseline;
- flows leave a box at its bottom-centre and enter at the target's top, through
  declared offsets — never "near" a box, always on its edge;
- the analysts' fan gathers on a shared bus and enters bull once, at its centre;
- debates are solid double-headed amber lines inside a labelled group; feedback
  (memory) is a dotted grey line routed along the canvas margin, outside the
  main flow.

Two layouts exist because the shape does not survive a 360px column: wide puts
the analysts in one row, narrow stacks the spine and keeps the debate pairs side
by side.
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
    "analyst_y": 52,
    "analyst_width": 150,
    "analyst_gap": 26,
    # The analyst row centres on bull (280 + 75 = 355): the gather reads as one
    # symmetric funnel whatever the selection.
    "centre": 355.0,
    "bus_y": 140.0,
    "default_width": 150,
    "boxes": {
        "memory": (720, 52),
        "bull": (280, 168),
        "bear": (530, 168),
        "research-manager": (405, 272),
        "trader": (405, 368),
        "risk-aggressive": (150, 464),
        "risk-conservative": (405, 464),
        "risk-neutral": (660, 464),
        "portfolio": (405, 560),
    },
    "margin_x": 944.0,
    "cycle_drop": 20,
    "groups": [
        {"id": "input", "label": "输入", "members": "analysts+memory",
         "x": 2, "y": 34, "w": 882, "h": 80},
        {"id": "research", "label": "研究辩论", "members": ["bull", "bear"],
         "x": 266, "y": 150, "w": 428, "h": 80},
        {"id": "risk", "label": "风险辩论 · 循环", "members":
            ["risk-aggressive", "risk-conservative", "risk-neutral"],
         "x": 136, "y": 444, "w": 688, "h": 100},
    ],
}

_NARROW = {
    "viewBox": "0 0 360 740",
    "height": 44,
    "analyst_y": 36,
    "analyst_width": 240,
    "analyst_x": 60,
    "analyst_gap": 16,
    "default_width": 240,
    "boxes": {
        "memory": (60, 616),
        "bull": (20, 316),
        "bear": (190, 316),
        "research-manager": (60, 400),
        "trader": (60, 468),
        "risk-aggressive": (20, 536),
        "risk-conservative": (130, 536),
        "risk-neutral": (240, 536),
        "portfolio": (60, 676),
    },
    "widths": {"bull": 150, "bear": 150,
               "risk-aggressive": 100, "risk-conservative": 100, "risk-neutral": 100},
    "margin_x": 8.0,
    "spine_x": 324.0,
    "bus_y": 288.0,
    "cycle_drop": 12,
    "exit_right": {("risk-neutral", "portfolio"): "M 340 558 H 352 V 698 H 300"},
    "groups": [
        {"id": "input", "label": "输入", "members": "analysts",
         "x": 48, "y": 24, "w": 264, "h": 248},
        {"id": "research", "label": "研究辩论", "members": ["bull", "bear"],
         "x": 6, "y": 296, "w": 348, "h": 80},
        {"id": "risk", "label": "风险辩论 · 循环", "members":
            ["risk-aggressive", "risk-conservative", "risk-neutral"],
         "x": 8, "y": 516, "w": 340, "h": 80},
    ],
}


def _n(value: float) -> str:
    return f"{value:g}"


def _analyst_row(spec: dict, analysts: list[str]) -> list[tuple[str, int, int]]:
    """The selected analysts' (key, x, y) triples for this layout.

    Wide centres the row on the debate entry whatever the selection; narrow
    stacks a fixed column so its lines can ride one spine.
    """
    selected = [key for key in ANALYST_ORDER if key in analysts]
    if "analyst_x" in spec:                      # narrow: fixed column, stacked
        return [(key, spec["analyst_x"], spec["analyst_y"]
                 + index * (spec["height"] + spec["analyst_gap"]))
                for index, key in enumerate(selected)]
    width = spec["analyst_width"]
    total = len(selected) * width + (len(selected) - 1) * spec["analyst_gap"]
    start = round(spec["centre"] - total / 2)
    return [(key, start + index * (width + spec["analyst_gap"]), spec["analyst_y"])
            for index, key in enumerate(selected)]


def _node(node_id: str, kernel: str, x: int, y: int, width: int, height: int) -> dict:
    label = NODE_LABELS[kernel]
    return {"id": node_id, "kernel": kernel, "label": label,
            "short": _SHORT.get(kernel, label),
            "x": x, "y": y, "w": width, "h": height}


def _build_nodes(spec: dict, analysts: list[str]) -> list[dict]:
    nodes = []
    for key, x, y in _analyst_row(spec, analysts):
        kernel = ANALYST_NODES[key]
        nodes.append(_node(f"analyst-{key}", kernel, x, y,
                           spec["analyst_width"], spec["height"]))
    analyst_end = nodes[-1]["x"] + nodes[-1]["w"] if nodes else 0
    for node_id, kernel in _CORE:
        x, y = spec["boxes"][node_id]
        if node_id == "memory" and "analyst_x" not in spec and nodes:
            x = analyst_end + spec["analyst_gap"]   # one gap after the analyst row
        width = spec.get("widths", {}).get(node_id, spec["default_width"])
        nodes.append(_node(node_id, kernel, x, y, width, spec["height"]))
    return nodes


def _centre_x(node: dict) -> float:
    return node["x"] + node["w"] / 2


def _drop(src: dict, dst: dict, to_x: float | None = None) -> str:
    """Down out of ``src``'s bottom port, across, down into ``dst``'s top."""
    x1 = _centre_x(src)
    x2 = _centre_x(dst) if to_x is None else to_x
    y1 = src["y"] + src["h"]
    mid = (y1 + dst["y"]) / 2
    return (f"M {_n(x1)} {_n(y1)} V {_n(mid)} H {_n(x2)} V {_n(dst['y'])}")


def _bus(src: dict, dst: dict, bus_y: float, spine_x: float | None) -> str:
    """Onto the shared bus, along it, then once down into the entry port.

    Wide: the bus is horizontal under the row. Narrow: the bus is a vertical
    spine beside the stacked column, and the shared run meets bull's centre.
    """
    entry = _centre_x(dst)
    if spine_x is None:
        return (f"M {_n(_centre_x(src))} {_n(src['y'] + src['h'])} V {_n(bus_y)} "
                f"H {_n(entry)} V {_n(dst['y'])}")
    return (f"M {_n(src['x'] + src['w'])} {_n(src['y'] + src['h'] / 2)} "
            f"H {_n(spine_x)} V {_n(bus_y)} H {_n(entry)} V {_n(dst['y'])}")


def _across(src: dict, dst: dict) -> str:
    """Straight across the row: the debate hand-off."""
    y = src["y"] + src["h"] / 2
    return f"M {_n(src['x'] + src['w'])} {_n(y)} H {_n(dst['x'])}"


def _return_arc(src: dict, dst: dict, drop: int) -> str:
    """Back under the row: the debate loop closing, inside its group."""
    y = src["y"] + src["h"] + drop
    return (f"M {_n(_centre_x(src) - 35)} {_n(src['y'] + src['h'])} V {_n(y)} "
            f"H {_n(_centre_x(dst) + 35)} V {_n(dst['y'] + dst['h'])}")


def _bypass(src: dict, dst: dict, margin: float) -> str:
    """Out to the margin and down: the memory log only reaches the portfolio."""
    if margin < src["x"]:
        x1, x2 = src["x"], dst["x"]
    else:
        x1, x2 = src["x"] + src["w"], dst["x"] + dst["w"]
    y1 = src["y"] + src["h"] / 2
    y2 = dst["y"] + dst["h"] / 2
    return f"M {_n(x1)} {_n(y1)} H {_n(margin)} V {_n(y2)} H {_n(x2)}"


def _edge(source: str, target: str, kind: str, path: str) -> dict:
    return {"from": source, "to": target, "kind": kind, "d": path}


def _edges(nodes: dict[str, dict], spec: dict) -> list[dict]:
    edges = []
    custom = spec.get("exit_right", {})
    analysts = [node_id for node_id in nodes if node_id.startswith("analyst-")]
    bull = nodes["bull"]
    # every analyst line rides the same bus and enters bull's centre port once
    for node_id in analysts:
        edges.append(_edge(node_id, "bull", "flow",
                           _bus(nodes[node_id], bull, spec["bus_y"],
                                spec.get("spine_x"))))
    edges.append(_edge("bull", "bear", "debate", _across(bull, nodes["bear"])))
    manager = nodes["research-manager"]
    for source, offset in (("bull", 1), ("bear", 2)):
        to_x = manager["x"] + manager["w"] * offset / 3
        edges.append(_edge(source, "research-manager", "flow",
                           _drop(nodes[source], manager, to_x)))
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
    route = custom.get(("risk-neutral", "portfolio"))
    edges.append(_edge("risk-neutral", "portfolio", "flow",
                       route or _drop(nodes["risk-neutral"], nodes["portfolio"])))
    edges.append(_edge("memory", "portfolio", "bypass",
                       _bypass(nodes["memory"], nodes["portfolio"], spec["margin_x"])))
    return edges


def _groups(spec: dict, nodes: dict[str, dict]) -> list[dict]:
    """The declared group rects with their member ids resolved."""
    groups = []
    for group in spec["groups"]:
        entry = dict(group)
        members = entry["members"]
        if members == "analysts+memory":
            entry["members"] = [node_id for node_id in nodes
                                if node_id.startswith("analyst-") or node_id == "memory"]
        elif members == "analysts":
            entry["members"] = [node_id for node_id in nodes
                                if node_id.startswith("analyst-")]
        else:
            entry["members"] = list(members)
        groups.append(entry)
    return groups


def _layout(spec: dict, analysts: list[str]) -> dict:
    nodes = _build_nodes(spec, analysts)
    by_id = {node["id"]: node for node in nodes}
    return {"viewBox": spec["viewBox"], "nodes": nodes,
            "edges": _edges(by_id, spec), "groups": _groups(spec, by_id)}


def topology(analysts: list[str] | None) -> dict:
    """Both layouts for the analysts this run selected."""
    selected = [key for key in ANALYST_ORDER if key in set(analysts or ())]
    return {"wide": _layout(_WIDE, selected), "narrow": _layout(_NARROW, selected)}
