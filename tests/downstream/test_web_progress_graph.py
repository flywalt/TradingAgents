"""The run drawn as a graph: topology and both layouts, computed in Python.

Layout lives here rather than in the browser so it can be tested: nodes must
not overlap, must stay inside the canvas, and every edge must join two nodes
that exist. The script in ``static/run-page.js`` only paints this and lights
it from the recorded events.
"""

from __future__ import annotations

import pytest

from tradingagents_web import progress_graph

pytestmark = pytest.mark.unit

ALL = ["market", "social", "news", "fundamentals"]


def _boxes(layout):
    return {n["id"]: n for n in layout["nodes"]}


def _target_ok(target, layout):
    """Edges may end on a node or on a group container's port."""
    if target in _boxes(layout):
        return True
    return target in {g["id"] for g in layout["groups"]}


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_the_layout_draws_every_core_node(width):
    ids = set(_boxes(progress_graph.topology(ALL)[width]))

    assert {"bull", "bear", "research-manager", "trader", "portfolio"} <= ids
    assert {"analyst-market", "analyst-social", "analyst-news", "analyst-fundamentals"} <= ids
    assert {"risk-aggressive", "risk-conservative", "risk-neutral", "memory"} <= ids


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_only_the_selected_analysts_are_drawn(width):
    layout = progress_graph.topology(["market"])[width]
    ids = set(_boxes(layout))

    assert "analyst-market" in ids
    assert not {"analyst-social", "analyst-news", "analyst-fundamentals"} & ids
    assert all(_target_ok(e["from"], layout) and _target_ok(e["to"], layout)
               for e in layout["edges"])


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_no_two_nodes_overlap(width):
    boxes = list(_boxes(progress_graph.topology(ALL)[width]).values())

    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            separated = (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                         or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])
            assert separated, (a["id"], b["id"])


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_every_node_fits_inside_the_viewbox(width):
    layout = progress_graph.topology(ALL)[width]
    _, _, width_px, height_px = (int(v) for v in layout["viewBox"].split())

    for node in layout["nodes"]:
        assert node["x"] >= 0 and node["y"] >= 0
        assert node["x"] + node["w"] <= width_px
        assert node["y"] + node["h"] <= height_px


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_every_edge_is_a_path_between_two_known_nodes(width):
    layout = progress_graph.topology(ALL)[width]

    for edge in layout["edges"]:
        assert _target_ok(edge["from"], layout) and _target_ok(edge["to"], layout)
        assert edge["d"].startswith("M ")
        assert edge["kind"] in {"flow", "debate", "bypass"}


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_the_debate_pairs_are_marked_as_debates(width):
    layout = progress_graph.topology(ALL)[width]
    pairs = {(e["from"], e["to"]) for e in layout["edges"] if e["kind"] == "debate"}

    assert ("bull", "bear") in pairs
    assert ("risk-aggressive", "risk-conservative") in pairs
    assert ("risk-conservative", "risk-neutral") in pairs
    assert ("risk-neutral", "risk-aggressive") in pairs if width == "narrow" \
        else ("risk-aggressive", "risk-neutral") in pairs


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_the_risk_trio_forms_a_closed_triangle(width):
    """Equal peers in a loop: drawn as a triangle, every corner on a box edge."""
    layout = progress_graph.topology(ALL)[width]
    boxes = _boxes(layout)
    trio = [e for e in layout["edges"] if e["kind"] == "debate"
            and e["from"].startswith("risk-")]
    assert len(trio) == 3

    for edge in trio:
        src, dst = boxes[edge["from"]], boxes[edge["to"]]
        parts = edge["d"].split(" ")
        if " L " in edge["d"]:                       # diagonal side of the triangle
            x1, y1 = (float(v) for v in parts[1:3])
            x2, y2 = (float(v) for v in parts[4:6])
        else:                                        # the level side (H or V)
            x1, y1 = (float(v) for v in parts[1:3])
            assert parts[3] in ("H", "V")
            if parts[3] == "H":
                x2, y2 = float(parts[4]), y1
            else:
                x2, y2 = x1, float(parts[4])
        on_src_edge = (y1 in (src["y"] + src["h"], src["y"] + src["h"] / 2)) and src["x"] <= x1 <= src["x"] + src["w"]
        on_dst_edge = (y2 in (dst["y"], dst["y"] + dst["h"], dst["y"] + dst["h"] / 2)) and dst["x"] <= x2 <= dst["x"] + dst["w"]
        assert on_src_edge and on_dst_edge, (edge, (x1, y1), (x2, y2))


def test_every_node_carries_its_kernel_name_and_chinese_label():
    bull = _boxes(progress_graph.topology(ALL)["wide"])["bull"]

    assert bull["kernel"] == "Bull Researcher"
    assert bull["label"] == "多头研究员"


@pytest.mark.parametrize("analysts", [
    ["market"],
    ["market", "social"],
    ["market", "social", "news"],
    ["market", "social", "news", "fundamentals"],
])
def test_the_analyst_column_sits_on_the_spine(analysts):
    """The gather reads as one symmetric funnel, whatever the selection."""
    layout = progress_graph.topology(analysts)["wide"]
    boxes = _boxes(layout)
    _, _, width_px, height_px = (int(v) for v in layout["viewBox"].split())
    spine = height_px / 2

    centres = [box["y"] + box["h"] / 2 for box in boxes.values()
               if box["id"].startswith("analyst-")]
    column_centre = (min(centres) + max(centres)) / 2
    assert abs(column_centre - spine) <= 1, (analysts, column_centre, spine)
    assert width_px == 1300                       # one screen wide, not tall


def test_wide_the_debate_stage_speaks_with_one_line():
    """The stage hands over as one line: the group's edge is the merge."""
    layout = progress_graph.topology(ALL)["wide"]
    boxes = _boxes(layout)
    groups = {g["id"]: g for g in layout["groups"]}
    manager = boxes["research-manager"]
    into_manager = [e for e in layout["edges"] if e["to"] == "research-manager"]

    assert [(e["from"], e["kind"]) for e in into_manager] == [("research", "flow")]
    research = groups["research"]
    assert into_manager[0]["d"] == (f"M {research['x'] + research['w']} "
                                    f"{layout['viewBox'].split()[3] and 215} "
                                    f"H {manager['x']}")


def test_narrow_the_debate_merges_into_one_line_before_the_manager():
    """Two debaters, one outcome: a shared merge line, a single entry drop."""
    layout = progress_graph.topology(ALL)["narrow"]
    boxes = _boxes(layout)
    manager = boxes["research-manager"]
    into_manager = [e for e in layout["edges"] if e["to"] == "research-manager"]

    assert {e["from"] for e in into_manager} == {"bull", "bear"}
    entries = set()
    for edge in into_manager:
        merge_y = edge["d"].split(" ")[3]
        assert edge["d"].endswith(f"V {manager['y']}")
        entries.add((merge_y, edge["d"].split(" H ")[-1].split(" ")[0]))
    assert len(entries) == 1                      # one merge line, one entry x


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_every_group_carries_the_same_frame(width):
    """One system: same label band above, same padding below, in every group."""
    layout = progress_graph.topology(ALL)[width]
    boxes = _boxes(layout)

    bands, feet = [], []
    for group in layout["groups"]:
        tops = [boxes[m]["y"] for m in group["members"]]
        bottoms = [boxes[m]["y"] + boxes[m]["h"] for m in group["members"]]
        bands.append(min(tops) - group["y"])
        feet.append(group["y"] + group["h"] - max(bottoms))
    assert len(set(bands)) == 1 and bands[0] == 26, (width, bands)
    assert len(set(feet)) == 1 and feet[0] == 26, (width, feet)


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_the_input_stage_hands_over_with_one_line(width):
    """Group to group: which analyst works shows on its card, not on the wire."""
    layout = progress_graph.topology(ALL)[width]
    groups = {g["id"]: g for g in layout["groups"]}

    stage_lines = [e for e in layout["edges"]
                   if e["from"] == "input" and e["to"] == "research"]
    assert len(stage_lines) == 1
    assert not [e for e in layout["edges"] if e["from"].startswith("analyst-")]
    # anchored on the group edges, on the axis of travel
    source, target = groups["input"], groups["research"]
    d = stage_lines[0]["d"]
    if width == "wide":
        assert d == f"M {source['x'] + source['w']:g} 215 H {target['x']:g}"
    else:
        assert d == (f"M {source['x'] + source['w'] / 2:g} "
                     f"{source['y'] + source['h']:g} V {target['y']:g}")
