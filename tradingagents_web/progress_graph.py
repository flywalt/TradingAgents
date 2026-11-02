"""The run drawn as a graph: topology, groups and both layouts, in Python.

Layout lives here rather than in the browser so it can be tested: nodes must not
overlap, must stay inside the canvas and their group, and every edge must join
two known targets (nodes or groups) through fixed ports.

Drawing grammar (what the viewer can rely on):

- one vertical spine per layout; every stage's boxes share a row and a baseline;
- flows leave a box at its bottom-centre and enter the target's top, through
  declared offsets — never "near" a box, always on its edge;
- the analysts' fan gathers on a shared bus and enters the research debate
  through the group's top-centre port: the run joins the *stage*, not one
  debater (the kernel starts the debate with the bull, which the events show);
- debates are solid double-headed amber lines. The risk trio is drawn as a
  closed triangle — three equal peers, each side an edge of the loop — so the
  cycle needs no return arc threading the main flow;
- the memory log is a feedback node in both layouts: outside the input group,
  beside the portfolio it feeds, connected only by a dotted line routed along
  the canvas margin.

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
    "viewBox": "0 0 960 770",
    "height": 48,
    "analyst_y": 60,
    "analyst_width": 150,
    "analyst_gap": 26,
    # The analyst row and both group entries share this spine, so the page has
    # one axis from the input row down to the portfolio.
    "centre": 480.0,
    "bus_y": 150.0,
    "merge_y": 268.0,
    "default_width": 150,
    "boxes": {
        # the memory log is a feedback node beside the portfolio it feeds,
        # not part of the input row - in both layouts, telling one story
        "memory": (720, 692),
        "bull": (303, 190),
        "bear": (493, 190),
        "research-manager": (405, 304),
        "trader": (405, 392),
        "risk-aggressive": (240, 498),
        "risk-conservative": (570, 498),
        "risk-neutral": (405, 588),
        "portfolio": (405, 692),
    },
    "margin_x": 944.0,
    # Every group opens with a label band before its boxes, so a label never
    # sits on top of a box.
    "groups": [
        {"id": "input", "label": "输入", "members": "analysts",
         "x": 127, "y": 34, "w": 706, "h": 94},
        {"id": "research", "label": "研究辩论", "members": ["bull", "bear"],
         "x": 289, "y": 164, "w": 382, "h": 92},
        {"id": "risk", "label": "风险辩论 · 循环", "members":
            ["risk-aggressive", "risk-conservative", "risk-neutral"],
         "x": 226, "y": 472, "w": 508, "h": 178},
    ],
}

_NARROW = {
    "viewBox": "0 0 360 930",
    "height": 44,
    "analyst_y": 50,
    "analyst_width": 240,
    "analyst_x": 60,
    "analyst_gap": 16,
    "merge_y": 424.0,
    "default_width": 240,
    "boxes": {
        "memory": (60, 860),
        "bull": (20, 344),
        "bear": (190, 344),
        "research-manager": (60, 456),
        "trader": (60, 524),
        "risk-aggressive": (20, 622),
        "risk-conservative": (190, 622),
        "risk-neutral": (105, 706),
        "portfolio": (60, 796),
    },
    "widths": {"bull": 150, "bear": 150,
               "risk-aggressive": 100, "risk-conservative": 100, "risk-neutral": 100},
    "margin_x": 8.0,
    "spine_x": 324.0,
    "bus_y": 310.0,
    "groups": [
        {"id": "input", "label": "输入", "members": "analysts",
         "x": 48, "y": 30, "w": 264, "h": 256},
        {"id": "research", "label": "研究辩论", "members": ["bull", "bear"],
         "x": 6, "y": 318, "w": 348, "h": 92},
        {"id": "risk", "label": "风险辩论 · 循环", "members":
            ["risk-aggressive", "risk-conservative", "risk-neutral"],
         "x": 8, "y": 596, "w": 344, "h": 168},
    ],
}


def _n(value: float) -> str:
    return f"{value:g}"


def _analyst_row(spec: dict, analysts: list[str]) -> list[tuple[str, int, int]]:
    """The selected analysts' (key, x, y) triples for this layout.

    Wide centres the row on the spine whatever the selection; narrow stacks a
    fixed column so its lines can ride one spine.
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
    for node_id, kernel in _CORE:
        x, y = spec["boxes"][node_id]
        width = spec.get("widths", {}).get(node_id, spec["default_width"])
        nodes.append(_node(node_id, kernel, x, y, width, spec["height"]))
    return nodes


def _centre_x(node: dict) -> float:
    return node["x"] + node["w"] / 2


def _enter(src: dict, port_x: float, port_y: float, via_y: float | None) -> str:
    """Leave the source's bottom port, gather at ``via_y``, enter ``port``."""
    x1 = _centre_x(src)
    y1 = src["y"] + src["h"]
    if via_y is None or abs(port_x - x1) < 0.5:
        return f"M {_n(x1)} {_n(y1)} V {_n(port_y)}"
    return f"M {_n(x1)} {_n(y1)} V {_n(via_y)} H {_n(port_x)} V {_n(port_y)}"


def _drop(src: dict, dst: dict, to_x: float | None = None) -> str:
    """Down out of ``src``'s bottom port, across, down into ``dst``'s top."""
    x1 = _centre_x(src)
    x2 = _centre_x(dst) if to_x is None else to_x
    y1 = src["y"] + src["h"]
    mid = (y1 + dst["y"]) / 2
    return (f"M {_n(x1)} {_n(y1)} V {_n(mid)} H {_n(x2)} V {_n(dst['y'])}")


def _across(src: dict, dst: dict) -> str:
    """Straight across the row: the debate hand-off."""
    y = src["y"] + src["h"] / 2
    return f"M {_n(src['x'] + src['w'])} {_n(y)} H {_n(dst['x'])}"


def _edge_ports(box: dict) -> dict:
    return {
        "bottom": (_centre_x(box), box["y"] + box["h"]),
        "top": (_centre_x(box), box["y"]),
        "left": (box["x"], box["y"] + box["h"] / 2),
        "right": (box["x"] + box["w"], box["y"] + box["h"] / 2),
    }


def _diagonal(src: dict, dst: dict, src_side: str, dst_side: str) -> str:
    """Corner to corner across a triangle: anchors on both box edges."""
    (x1, y1) = _edge_ports(src)[src_side]
    (x2, y2) = _edge_ports(dst)[dst_side]
    return f"M {_n(x1)} {_n(y1)} L {_n(x2)} {_n(y2)}"


def _bypass(src: dict, dst: dict, margin: float) -> str:
    """The memory log only reaches the portfolio.

    Beside it (wide): a short dotted line straight across. Under it (narrow):
    out to the canvas margin and around, clear of the main flow.
    """
    y1 = src["y"] + src["h"] / 2
    y2 = dst["y"] + dst["h"] / 2
    if abs(y1 - y2) < 1:
        return f"M {_n(src['x'])} {_n(y1)} H {_n(dst['x'] + dst['w'])}"
    if margin < src["x"]:
        x1, x2 = src["x"], dst["x"]
    else:
        x1, x2 = src["x"] + src["w"], dst["x"] + dst["w"]
    return f"M {_n(x1)} {_n(y1)} H {_n(margin)} V {_n(y2)} H {_n(x2)}"


def _edge(source: str, target: str, kind: str, path: str) -> dict:
    return {"from": source, "to": target, "kind": kind, "d": path}


def _edges(nodes: dict[str, dict], spec: dict) -> list[dict]:
    edges = []
    groups = {g["id"]: g for g in spec["groups"]}
    analysts = [node_id for node_id in nodes if node_id.startswith("analyst-")]

    # the run joins the debate stage through the group's top-centre port
    research = groups["research"]
    for node_id in analysts:
        edges.append(_edge(node_id, "research", "flow",
                           _enter(nodes[node_id], research["x"] + research["w"] / 2,
                                  research["y"], spec["bus_y"])))
    edges.append(_edge("bull", "bear", "debate", _across(nodes["bull"], nodes["bear"])))
    # the debate's outcome is one thing: both debaters meet a shared merge line
    # and a single drop enters the manager - not two competing elbows
    manager = nodes["research-manager"]
    entry = _centre_x(manager)
    for source in ("bull", "bear"):
        src = nodes[source]
        x1 = _centre_x(src)
        y1 = src["y"] + src["h"]
        edges.append(_edge(source, "research-manager", "flow",
                           f"M {_n(x1)} {_n(y1)} V {_n(spec['merge_y'])} "
                           f"H {_n(entry)} V {_n(manager['y'])}"))
    edges.append(_edge("research-manager", "trader", "flow",
                       _drop(nodes["research-manager"], nodes["trader"])))

    # into the risk loop through its group port as well
    risk = groups["risk"]
    edges.append(_edge("trader", "risk", "flow",
                       _enter(nodes["trader"], risk["x"] + risk["w"] / 2,
                              risk["y"], None)))

    # three equal peers, closed triangle: across the top, then the two slopes
    edges.append(_edge("risk-aggressive", "risk-conservative", "debate",
                       _across(nodes["risk-aggressive"], nodes["risk-conservative"])))
    edges.append(_edge("risk-conservative", "risk-neutral", "debate",
                       _diagonal(nodes["risk-conservative"], nodes["risk-neutral"],
                                 "bottom", "right")))
    edges.append(_edge("risk-neutral", "risk-aggressive", "debate",
                       _diagonal(nodes["risk-neutral"], nodes["risk-aggressive"],
                                 "left", "bottom")))

    edges.append(_edge("risk-neutral", "portfolio", "flow",
                       _drop(nodes["risk-neutral"], nodes["portfolio"])))
    edges.append(_edge("memory", "portfolio", "bypass",
                       _bypass(nodes["memory"], nodes["portfolio"], spec["margin_x"])))
    return edges


def _groups(spec: dict, nodes: dict[str, dict]) -> list[dict]:
    """The declared group rects with their member ids resolved."""
    groups = []
    for group in spec["groups"]:
        entry = dict(group)
        members = entry["members"]
        if members == "analysts":
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
