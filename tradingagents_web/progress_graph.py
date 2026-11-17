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
    # Horizontal: the stages hand over left to right, each stage's boxes stack
    # vertically (the risk trio keeps its triangle). One screen, one line of
    # travel, and one measure between stages so the hand-offs read as equals.
    #
    # Only the constants that the flow is built from live here; the coordinates
    # themselves are derived in ``_wide_spec`` (one gutter, one stage gap), so
    # there is no second copy of the layout to drift.
    "viewBox": "0 0 1310 430",
    "orient": "h",
    #: A 13px label in a 40px card: 13.5px of air above and below. 48 left the
    #: cards looking like empty chips next to the rest of the page's rhythm.
    "height": 40,
    "analyst_width": 130,
    "analyst_gap": 16,
    "spine_y": 215.0,
    "stage_gap": 48,
}

_NARROW = {
    # Narrow: one vertical spine. The whole flow is computed in ``_narrow_spec``
    # from the card count, so a one-analyst run draws a short page instead of a
    # four-analyst column with three empty rows.
    "viewBox": "0 0 360 910",
    "height": 40,
    "analyst_width": 240,
    "analyst_x": 60,
    "analyst_gap": 16,
    "stage_gap": 24,
    "margin_x": 8.0,
    "default_width": 240,
}


def _n(value: float) -> str:
    return f"{value:g}"


def _analyst_row(spec: dict, analysts: list[str]) -> list[tuple[str, int, int]]:
    """The selected analysts' (key, x, y) triples for this layout.

    Wide stacks them centred on the horizontal spine whatever the selection;
    narrow stacks its fixed column the same way. A lone analyst sits on the
    spine either way.
    """
    selected = [key for key in ANALYST_ORDER if key in analysts]
    step = spec["height"] + spec["analyst_gap"]
    if spec.get("orient") == "h":                # wide: one column on the spine
        start = round(spec["spine_y"] - (len(selected) * spec["height"]
                                         + (len(selected) - 1) * spec["analyst_gap"]) / 2)
        return [(key, spec["analyst_x"], start + index * step)
                for index, key in enumerate(selected)]
    # narrow: the same fixed column, stacked from the top
    return [(key, spec["analyst_x"], spec["analyst_y"] + index * step)
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
        box = spec["boxes"][node_id]
        x, y = box[0], box[1]
        width = box[2] if len(box) > 2 else spec.get(
            "widths", {}).get(node_id, spec["default_width"])
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
    groups = {g["id"]: g for g in spec["groups"]}
    if spec.get("orient") == "h":
        return _edges_horizontal(nodes, spec, groups)
    return _edges_vertical(nodes, spec, groups)


def _right_of(group_or_node: dict) -> float:
    return group_or_node["x"] + group_or_node["w"]


def _edges_horizontal(nodes: dict[str, dict], spec: dict, groups: dict) -> list[dict]:
    """The wide picture: stages hand over left to right along one spine.

    A stage speaks with one voice - its group - so each hand-off is a single
    line from the group's edge, which is also the debate's merge.
    """
    edges = []
    research, risk = groups["research"], groups["risk"]
    spine = spec["spine_y"]

    # one stage line: the input group as a whole hands over to the debate
    # stage. Which analysts are working shows on their cards, not on the wire.
    input_group = groups["input"]
    edges.append(_edge("input", "research", "flow",
                       f"M {_n(_right_of(input_group))} {_n(spine)} "
                       f"H {_n(research['x'])}"))
    edges.append(_edge("bull", "bear", "debate",
                       f"M {_n(_centre_x(nodes['bull']))} {_n(nodes['bull']['y'] + nodes['bull']['h'])} "
                       f"V {_n(nodes['bear']['y'])}"))
    edges.append(_edge("research", "research-manager", "flow",
                       f"M {_n(_right_of(research))} {_n(spine)} H {_n(nodes['research-manager']['x'])}"))
    edges.append(_edge("research-manager", "trader", "flow",
                       f"M {_n(_right_of(nodes['research-manager']))} {_n(spine)} "
                       f"H {_n(nodes['trader']['x'])}"))
    edges.append(_edge("trader", "risk", "flow",
                       f"M {_n(_right_of(nodes['trader']))} {_n(spine)} H {_n(risk['x'])}"))
    # the triangle: a level left side, two slopes to the apex
    edges.append(_edge("risk-aggressive", "risk-conservative", "debate",
                       f"M {_n(_centre_x(nodes['risk-aggressive']))} "
                       f"{_n(nodes['risk-aggressive']['y'] + nodes['risk-aggressive']['h'])} "
                       f"V {_n(nodes['risk-conservative']['y'])}"))
    edges.append(_edge("risk-aggressive", "risk-neutral", "debate",
                       _diagonal(nodes["risk-aggressive"], nodes["risk-neutral"], "right", "top")))
    edges.append(_edge("risk-conservative", "risk-neutral", "debate",
                       _diagonal(nodes["risk-conservative"], nodes["risk-neutral"], "right", "bottom")))
    edges.append(_edge("risk", "portfolio", "flow",
                       f"M {_n(_right_of(risk))} {_n(spine)} H {_n(nodes['portfolio']['x'])}"))
    # feedback: straight up into the portfolio's bottom port
    memory = nodes["memory"]
    edges.append(_edge("memory", "portfolio", "bypass",
                       f"M {_n(_centre_x(memory))} {_n(memory['y'])} "
                       f"V {_n(nodes['portfolio']['y'] + nodes['portfolio']['h'])}"))
    return edges


def _edges_vertical(nodes: dict[str, dict], spec: dict, groups: dict) -> list[dict]:
    """The narrow picture: one vertical spine, debate pairs side by side."""
    edges = []
    research, risk = groups["research"], groups["risk"]

    # one stage line, as in the wide picture: group to group
    input_group = groups["input"]
    edges.append(_edge("input", "research", "flow",
                       f"M {_n(input_group['x'] + input_group['w'] / 2)} "
                       f"{_n(input_group['y'] + input_group['h'])} "
                       f"V {_n(research['y'])}"))
    edges.append(_edge("bull", "bear", "debate", _across(nodes["bull"], nodes["bear"])))
    # a debate hands over as one thing: the manager reads the whole exchange,
    # not one debater's take - so the group speaks, as in the wide picture
    manager = nodes["research-manager"]
    edges.append(_edge("research", "research-manager", "flow",
                       f"M {_n(research['x'] + research['w'] / 2)} "
                       f"{_n(research['y'] + research['h'])} V {_n(manager['y'])}"))
    edges.append(_edge("research-manager", "trader", "flow",
                       _drop(nodes["research-manager"], nodes["trader"])))
    edges.append(_edge("trader", "risk", "flow",
                       _enter(nodes["trader"], risk["x"] + risk["w"] / 2, risk["y"], None)))
    edges.append(_edge("risk-aggressive", "risk-conservative", "debate",
                       _across(nodes["risk-aggressive"], nodes["risk-conservative"])))
    edges.append(_edge("risk-conservative", "risk-neutral", "debate",
                       _diagonal(nodes["risk-conservative"], nodes["risk-neutral"], "bottom", "right")))
    edges.append(_edge("risk-neutral", "risk-aggressive", "debate",
                       _diagonal(nodes["risk-neutral"], nodes["risk-aggressive"], "left", "bottom")))
    # the risk loop concludes as one decision as well
    edges.append(_edge("risk", "portfolio", "flow",
                       f"M {_n(risk['x'] + risk['w'] / 2)} "
                       f"{_n(risk['y'] + risk['h'])} V {_n(nodes['portfolio']['y'])}"))
    edges.append(_edge("memory", "portfolio", "bypass",
                       _bypass(nodes["memory"], nodes["portfolio"], spec["margin_x"])))
    return edges


def _groups(spec: dict, nodes: dict[str, dict]) -> list[dict]:
    """The declared group rects with their member ids resolved.

    The vertical extent is then taken from the cards themselves: a frame is
    always a 26px band, its cards, and a 26px foot. That is what stops a
    one-analyst run from being drawn inside a four-analyst box.
    """
    groups = []
    for group in spec["groups"]:
        entry = dict(group)
        members = entry["members"]
        if members == "analysts":
            entry["members"] = [node_id for node_id in nodes
                                if node_id.startswith("analyst-")]
        else:
            entry["members"] = list(members)
        cards = [nodes[node_id] for node_id in entry["members"] if node_id in nodes]
        if cards:
            top = min(card["y"] for card in cards)
            bottom = max(card["y"] + card["h"] for card in cards)
            entry["y"] = top - _BAND
            entry["h"] = bottom - top + _BAND + _FOOT
        groups.append(entry)
    return groups


#: Frame geometry, in one place: a group carries a 26px label band above its
#: cards and 26px of foot below them, whatever the cards are.
_BAND = 26
_FOOT = 26
#: Narrow flow: 24 between stages, 80 between the risk triangle's two rows, and
#: a wider gap before the memory log (the feedback line runs through it).
_STAGE_GAP = 24
_RISK_STAGGER = 80
_MEMORY_GAP = 62
_CANVAS_PAD = 20
_TOP_MARGIN = 24


def _column_height(spec: dict, count: int) -> int:
    """How tall a stack of analyst cards is (one card's worth when none)."""
    count = max(count, 1)
    return count * spec["height"] + (count - 1) * spec["analyst_gap"]


def _wide_spec(spec: dict, count: int) -> dict:
    """Wide: the input frame follows the selection; the stage flow is fixed.

    The x axis is derived rather than typed in: one 14px gutter inside every
    frame, 48 between stages. Same flow as the hand-tuned coordinates, without
    the two-pixel drift they had (the risk frame was a hair narrower than its
    cards).
    """
    placed = dict(spec)
    column = _column_height(spec, count)
    top = round(spec["spine_y"] - column / 2)

    edge, gap, tri = 14, 48, 150
    analyst_w = spec["analyst_width"]

    input_x = 6
    analyst_x = input_x + edge
    input_w = analyst_w + 2 * edge
    research_x = input_x + input_w + gap
    debate_w = 150
    research_w = debate_w + 2 * edge
    manager_x = research_x + research_w + gap
    manager_w = 140
    trader_x = manager_x + manager_w + gap
    trader_w = 140
    risk_x = trader_x + trader_w + gap
    risk_card_w = 120
    risk_w = risk_card_w + tri + 2 * edge
    portfolio_x = risk_x + risk_w + gap
    portfolio_w = 140
    risk_card_x = risk_x + edge

    placed["analyst_x"] = analyst_x      # single source: the input frame's gutter
    placed["boxes"] = {
        "memory": (portfolio_x, 304, portfolio_w),
        "bull": (research_x + edge, 156, debate_w),
        "bear": (research_x + edge, 234, debate_w),
        "research-manager": (manager_x, 195, manager_w),
        "trader": (trader_x, 195, trader_w),
        "risk-aggressive": (risk_card_x, 124, risk_card_w),
        "risk-conservative": (risk_card_x, 266, risk_card_w),
        "risk-neutral": (risk_card_x + tri, 195, risk_card_w),
        "portfolio": (portfolio_x, 195, portfolio_w),
    }
    placed["groups"] = [
        {"id": "input", "label": "输入", "members": "analysts",
         "x": input_x, "y": top - _BAND, "w": input_w,
         "h": column + _BAND + _FOOT},
        # y/h are placeholders: _groups() takes them from the cards.
        {"id": "research", "label": "研究辩论", "members": ["bull", "bear"],
         "x": research_x, "w": research_w},
        {"id": "risk", "label": "风险辩论 · 循环", "members":
            ["risk-aggressive", "risk-conservative", "risk-neutral"],
         "x": risk_x, "w": risk_w},
    ]
    return placed


def _narrow_spec(spec: dict, count: int) -> dict:
    """Narrow: one column, so the whole page reflows with the selection.

    Four analysts reproduce the hand-tuned coordinates exactly (input 24..284,
    research 308..400, manager 424, trader 488, risk 552..724, portfolio 748,
    memory 850, canvas 910); fewer analysts simply shorten the page instead of
    leaving an empty input frame behind.
    """
    placed = dict(spec)
    column = _column_height(spec, count)
    card = spec["height"]

    analyst_y = _TOP_MARGIN + _BAND
    input_y = _TOP_MARGIN
    input_h = column + _BAND + _FOOT
    research_y = input_y + input_h + _STAGE_GAP
    research_h = card + _BAND + _FOOT
    manager_y = research_y + research_h + _STAGE_GAP
    trader_y = manager_y + card + _STAGE_GAP
    risk_y = trader_y + card + _STAGE_GAP
    risk_h = _RISK_STAGGER + card + _BAND + _FOOT
    portfolio_y = risk_y + risk_h + _STAGE_GAP
    memory_y = portfolio_y + card + _MEMORY_GAP
    canvas = memory_y + card + _CANVAS_PAD

    placed["analyst_y"] = analyst_y
    placed["viewBox"] = f"0 0 360 {canvas}"
    placed["boxes"] = {
        "memory": (60, memory_y),
        "bull": (20, research_y + _BAND, 150),
        "bear": (190, research_y + _BAND, 150),
        "research-manager": (60, manager_y),
        "trader": (60, trader_y),
        "risk-aggressive": (45, risk_y + _BAND, 100),
        "risk-conservative": (215, risk_y + _BAND, 100),
        "risk-neutral": (130, risk_y + _BAND + _RISK_STAGGER, 100),
        "portfolio": (60, portfolio_y),
    }
    placed["groups"] = [
        {"id": "input", "label": "输入", "members": "analysts",
         "x": 46, "y": input_y, "w": 268, "h": input_h},
        {"id": "research", "label": "研究辩论", "members": ["bull", "bear"],
         "x": 6, "y": research_y, "w": 348, "h": research_h},
        {"id": "risk", "label": "风险辩论 · 循环", "members":
            ["risk-aggressive", "risk-conservative", "risk-neutral"],
         "x": 31, "y": risk_y, "w": 298, "h": risk_h},
    ]
    return placed


def _placed_spec(spec: dict, analysts: list[str]) -> dict:
    """The declared layout, resolved for how many analysts this run selected."""
    if spec.get("orient") == "h":
        return _wide_spec(spec, len(analysts))
    return _narrow_spec(spec, len(analysts))


def _layout(spec: dict, analysts: list[str]) -> dict:
    placed = _placed_spec(spec, analysts)
    nodes = _build_nodes(placed, analysts)
    by_id = {node["id"]: node for node in nodes}
    return {"viewBox": placed["viewBox"], "nodes": nodes,
            "edges": _edges(by_id, placed), "groups": _groups(placed, by_id)}


def topology(analysts: list[str] | None) -> dict:
    """Both layouts for the analysts this run selected."""
    selected = [key for key in ANALYST_ORDER if key in set(analysts or ())]
    return {"wide": _layout(_WIDE, selected), "narrow": _layout(_NARROW, selected)}
