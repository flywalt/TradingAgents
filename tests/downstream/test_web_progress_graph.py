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
    assert all(e["from"] in ids and e["to"] in ids for e in layout["edges"])


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
    ids = set(_boxes(layout))

    for edge in layout["edges"]:
        assert edge["from"] in ids and edge["to"] in ids
        assert edge["d"].startswith("M ")
        assert edge["kind"] in {"flow", "debate", "bypass"}


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_the_debate_pairs_are_marked_as_debates(width):
    layout = progress_graph.topology(ALL)[width]
    pairs = {(e["from"], e["to"]) for e in layout["edges"] if e["kind"] == "debate"}

    assert ("bull", "bear") in pairs
    assert ("risk-aggressive", "risk-conservative") in pairs
    assert ("risk-conservative", "risk-neutral") in pairs
    assert ("risk-neutral", "risk-aggressive") in pairs


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
def test_the_analyst_row_is_centred_on_the_debate_entry(analysts):
    """The fan-in reads as one symmetric gather, whatever the selection."""
    boxes = _boxes(progress_graph.topology(analysts)["wide"])
    bull_centre = boxes["bull"]["x"] + boxes["bull"]["w"] / 2
    centres = [box["x"] + box["w"] / 2 for box in boxes.values()
               if box["id"].startswith("analyst-")]

    row_centre = (min(centres) + max(centres)) / 2
    assert abs(row_centre - bull_centre) <= 1, (analysts, row_centre, bull_centre)


ALL_IDS = {"analyst-market", "analyst-social", "analyst-news", "analyst-fundamentals",
           "memory", "bull", "bear", "research-manager", "trader",
           "risk-aggressive", "risk-conservative", "risk-neutral", "portfolio"}


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_the_three_groups_exist_and_carry_their_members(width):
    layout = progress_graph.topology(ALL)[width]
    groups = {g["id"]: g for g in layout["groups"]}
    boxes = _boxes(layout)

    assert {"input", "research", "risk"} <= set(groups)
    assert groups["research"]["label"] == "研究辩论"
    for member in ("bull", "bear"):
        assert member in groups["research"]["members"]
    for member in ("risk-aggressive", "risk-conservative", "risk-neutral"):
        assert member in groups["risk"]["members"]


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_every_member_sits_inside_its_group(width):
    layout = progress_graph.topology(ALL)[width]
    boxes = _boxes(layout)

    for group in layout["groups"]:
        for member in group["members"]:
            box = boxes[member]
            assert box["x"] >= group["x"] and box["y"] >= group["y"], (member, "nw")
            assert box["x"] + box["w"] <= group["x"] + group["w"], (member, "e")
            assert box["y"] + box["h"] <= group["y"] + group["h"], (member, "s")


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_groups_do_not_overlap_each_other(width):
    layout = progress_graph.topology(ALL)[width]

    for i, a in enumerate(layout["groups"]):
        for b in layout["groups"][i + 1:]:
            separated = (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                         or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])
            assert separated, (a["id"], b["id"])


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_the_analyst_fan_converges_through_one_shared_bus(width):
    """Every analyst's line drops onto the same horizontal and enters bull once."""
    layout = progress_graph.topology(ALL)[width]
    boxes = _boxes(layout)
    bull = boxes["bull"]
    edges = [e for e in layout["edges"] if e["to"] == "bull" and e["kind"] == "flow"]

    assert len(edges) == 4
    ends = set()
    for edge in edges:
        # last vertical run lands on bull's top edge
        tail = edge["d"].rsplit("V ", 1)[1]
        ends.add(tail)
        assert f"V {tail}" in edge["d"]
        assert float(tail) == bull["y"], tail
    assert len(ends) == 1
    # the entry x is bull's centre: the bus meets the box where its port is
    centre = f"{bull['x'] + bull['w'] / 2:g}"
    assert all(f"H {centre}" in e["d"] for e in edges)


@pytest.mark.parametrize("width", ["wide", "narrow"])
def test_vertical_flow_edges_leave_from_the_bottom_centre(width):
    """Fixed ports: a flow edge starts where its source box ends."""
    layout = progress_graph.topology(ALL)[width]
    boxes = _boxes(layout)

    for edge in layout["edges"]:
        if edge["kind"] != "flow" or edge["from"].startswith("analyst-"):
            continue
        src = boxes[edge["from"]]
        head = edge["d"].split(" ")[0:3]
        assert head[0] == "M"
        x1, y1 = float(head[1]), float(head[2])
        # fixed ports: bottom-centre by default; a box whose bottom port is
        # blocked (memory sits under the neutral) may exit right-centre
        bottom = (x1 == src["x"] + src["w"] / 2 and y1 == src["y"] + src["h"])
        right = (y1 == src["y"] + src["h"] / 2 and x1 == src["x"] + src["w"])
        assert bottom or right, (edge["from"], head)
