"""
PCB Parser Module
Parses .kicad_pcb files (S-expression format) into structured Python objects.
Supports KiCad version 6, 7, and 8 file formats.
"""

from __future__ import annotations
import re
import math
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────

@dataclass
class Point:
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def __iter__(self):
        yield self.x
        yield self.y


@dataclass
class Trace:
    start: Point
    end: Point
    width: float          # mm
    layer: str
    net: int
    net_name: str = ""

    @property
    def length(self) -> float:
        return self.start.distance_to(self.end)

    @property
    def center(self) -> Point:
        return Point((self.start.x + self.end.x) / 2,
                     (self.start.y + self.end.y) / 2)


@dataclass
class Via:
    position: Point
    drill: float          # mm
    size: float           # mm
    layers: list[str]
    net: int
    net_name: str = ""


@dataclass
class Pad:
    position: Point
    size_x: float
    size_y: float
    pad_type: str         # "smd", "thru_hole", "connect"
    shape: str
    layers: list[str]
    net: int
    net_name: str = ""
    component_ref: str = ""


@dataclass
class Zone:
    """Filled copper zone / ground plane."""
    layer: str
    net: int
    net_name: str
    polygon: list[Point]  # outline vertices

    @property
    def bounding_box(self) -> tuple[float, float, float, float]:
        xs = [p.x for p in self.polygon]
        ys = [p.y for p in self.polygon]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass
class Component:
    reference: str
    value: str
    position: Point
    layer: str
    rotation: float = 0.0
    pads: list[Pad] = field(default_factory=list)


@dataclass
class PCBBoard:
    """Top-level container for all parsed PCB data."""
    file_path: str
    title: str = ""
    width: float = 0.0    # mm
    height: float = 0.0   # mm
    origin: Point = field(default_factory=lambda: Point(0, 0))

    layers: list[str] = field(default_factory=list)
    traces: list[Trace] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    pads: list[Pad] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    components: list[Component] = field(default_factory=list)
    nets: dict[int, str] = field(default_factory=dict)   # id → name

    @property
    def copper_layers(self) -> list[str]:
        return [l for l in self.layers if l.startswith("F.Cu") or
                l.startswith("B.Cu") or re.match(r"In\d+\.Cu", l)]

    @property
    def ground_nets(self) -> list[int]:
        return [nid for nid, name in self.nets.items()
                if "GND" in name.upper() or "GROUND" in name.upper()]

    @property
    def power_nets(self) -> set[int]:
        """Net IDs that appear to be power supply nets."""
        power_prefixes = ('+', 'VCC', 'VDD', 'PWR', 'VBAT', 'V_')
        power_patterns = ('3V3', '3.3V', '5V', '12V', '1V8', '1.8V',
                          '2V5', '2.5V', 'VBUS', 'VSYS', 'VREF')
        result = set()
        for net_id, name in self.nets.items():
            name_upper = name.upper()
            if any(name_upper.startswith(p.upper()) for p in power_prefixes):
                result.add(net_id)
            elif any(p in name_upper for p in power_patterns):
                result.add(net_id)
        return result


# ─────────────────────────────────────────────────────────────
# S-expression tokenizer (zero-dependency, pure Python)
# ─────────────────────────────────────────────────────────────

def _tokenize(text: str) -> list:
    """Convert KiCad S-expression text into a nested list tree."""
    tokens = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c in ' \t\n\r':
            i += 1
        elif c == '(':
            tokens.append('(')
            i += 1
        elif c == ')':
            tokens.append(')')
            i += 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n:
                if text[j] == '\\' and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                elif text[j] == '"':
                    j += 1
                    break
                else:
                    buf.append(text[j])
                    j += 1
            tokens.append(''.join(buf))
            i = j
        else:
            j = i
            while j < n and text[j] not in ' \t\n\r()\"':
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _build_tree(tokens: list, pos: int = 0) -> tuple:
    """Recursively build a tree from flat token list."""
    result = []
    while pos < len(tokens):
        tok = tokens[pos]
        if tok == '(':
            pos += 1
            subtree, pos = _build_tree(tokens, pos)
            result.append(subtree)
        elif tok == ')':
            return result, pos + 1
        else:
            result.append(tok)
            pos += 1
    return result, pos


def _parse_sexp(text: str) -> list:
    tokens = _tokenize(text)
    tree, _ = _build_tree(tokens)
    return tree[0] if tree else []


# ─────────────────────────────────────────────────────────────
# Helpers for navigating the tree
# ─────────────────────────────────────────────────────────────

def _find(node: list, key: str) -> Optional[list]:
    """Return first child node whose first element equals key."""
    if not isinstance(node, list):
        return None
    for child in node:
        if isinstance(child, list) and child and child[0] == key:
            return child
    return None


def _find_all(node: list, key: str) -> list[list]:
    """Return all child nodes whose first element equals key."""
    if not isinstance(node, list):
        return []
    return [child for child in node
            if isinstance(child, list) and child and child[0] == key]


def _val(node: list, key: str, default=None):
    """Return the second element of a named child node."""
    child = _find(node, key)
    if child and len(child) > 1:
        return child[1]
    return default


def _float(node: list, key: str, default: float = 0.0) -> float:
    v = _val(node, key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _pt(node: list) -> Point:
    """Parse (xy x y) or (at x y ...) node."""
    try:
        return Point(float(node[1]), float(node[2]))
    except (IndexError, TypeError, ValueError):
        return Point(0.0, 0.0)


# ─────────────────────────────────────────────────────────────
# Main parser
# ─────────────────────────────────────────────────────────────

class KiCadPCBParser:
    """Parses a .kicad_pcb file and returns a PCBBoard object."""

    def parse_file(self, path: str | Path) -> PCBBoard:
        path = Path(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        return self.parse_text(text, str(path))

    def parse_text(self, text: str, source: str = "") -> PCBBoard:
        root = _parse_sexp(text)
        board = PCBBoard(file_path=source)
        if not root or root[0] != "kicad_pcb":
            raise ValueError("Not a valid .kicad_pcb file")

        self._parse_general(root, board)
        self._parse_layers(root, board)
        self._parse_nets(root, board)
        self._parse_segments(root, board)
        self._parse_vias(root, board)
        self._parse_footprints(root, board)
        self._parse_zones(root, board)
        self._compute_board_size(root, board)
        return board

    # ── sub-parsers ───────────────────────────────────────────

    def _parse_general(self, root: list, board: PCBBoard):
        gen = _find(root, "general")
        if gen:
            board.title = _val(gen, "title") or ""

    def _parse_layers(self, root: list, board: PCBBoard):
        layers_node = _find(root, "layers")
        if not layers_node:
            return
        for child in layers_node:
            if isinstance(child, list) and len(child) >= 3:
                # (id "name" type)
                name = child[1] if len(child) > 1 else ""
                board.layers.append(str(name))

    def _parse_nets(self, root: list, board: PCBBoard):
        for net_node in _find_all(root, "net"):
            try:
                nid = int(net_node[1])
                name = net_node[2] if len(net_node) > 2 else ""
                board.nets[nid] = str(name)
            except (IndexError, ValueError):
                pass

    def _parse_segments(self, root: list, board: PCBBoard):
        for seg in _find_all(root, "segment"):
            start_node = _find(seg, "start")
            end_node = _find(seg, "end")
            if not start_node or not end_node:
                continue
            start = _pt(start_node)
            end = _pt(end_node)
            width = _float(seg, "width", 0.2)
            layer = _val(seg, "layer", "F.Cu")
            net_id = int(_val(seg, "net", 0) or 0)
            trace = Trace(
                start=start, end=end,
                width=width, layer=str(layer),
                net=net_id,
                net_name=board.nets.get(net_id, "")
            )
            board.traces.append(trace)

    def _parse_vias(self, root: list, board: PCBBoard):
        for via_node in _find_all(root, "via"):
            at = _find(via_node, "at")
            if not at:
                continue
            pos = _pt(at)
            drill = _float(via_node, "drill", 0.3)
            size = _float(via_node, "size", 0.6)
            net_id = int(_val(via_node, "net", 0) or 0)
            layers_node = _find(via_node, "layers")
            layers = []
            if layers_node:
                layers = [str(l) for l in layers_node[1:]]
            board.vias.append(Via(
                position=pos, drill=drill, size=size,
                layers=layers, net=net_id,
                net_name=board.nets.get(net_id, "")
            ))

    def _parse_footprints(self, root: list, board: PCBBoard):
        for fp_node in _find_all(root, "footprint"):
            ref_node = None
            val_node = None
            # Find reference and value from fp_text children
            for child in _find_all(fp_node, "fp_text"):
                if len(child) > 2 and child[1] == "reference":
                    ref_node = child[2]
                elif len(child) > 2 and child[1] == "value":
                    val_node = child[2]

            # KiCad 8+: 'property' nodes replace 'fp_text'
            if not ref_node:
                for prop in _find_all(fp_node, 'property'):
                    if len(prop) >= 3 and prop[1] == 'Reference':
                        ref_node = prop[2]
            if not val_node:
                for prop in _find_all(fp_node, 'property'):
                    if len(prop) >= 3 and prop[1] == 'Value':
                        val_node = prop[2]

            at = _find(fp_node, "at")
            pos = _pt(at) if at else Point(0, 0)
            # Extract rotation from (at x y rotation) node
            comp_rotation = 0.0
            if at and len(at) > 3:
                try:
                    comp_rotation = float(at[3])
                except (ValueError, TypeError):
                    pass
            layer = _val(fp_node, "layer", "F.Cu")

            comp = Component(
                reference=str(ref_node or ""),
                value=str(val_node or ""),
                position=pos,
                layer=str(layer),
                rotation=comp_rotation
            )

            # Parse pads inside footprint
            for pad_node in _find_all(fp_node, "pad"):
                pad = self._parse_pad(pad_node, comp, board)
                if pad:
                    comp.pads.append(pad)
                    board.pads.append(pad)

            board.components.append(comp)

    def _parse_pad(self, pad_node: list, comp: Component,
                   board: PCBBoard) -> Optional[Pad]:
        try:
            pad_type = pad_node[2] if len(pad_node) > 2 else "smd"
            shape = pad_node[3] if len(pad_node) > 3 else "rect"
            at = _find(pad_node, "at")
            size_node = _find(pad_node, "size")
            if not at or not size_node:
                return None
            pad_offset = _pt(at)
            pad_x = pad_offset.x
            pad_y = pad_offset.y
            # Apply component rotation to pad offset
            comp_rotation = comp.rotation
            if comp_rotation != 0:
                angle_rad = math.radians(comp_rotation)
                cos_a = math.cos(angle_rad)
                sin_a = math.sin(angle_rad)
                rotated_x = pad_x * cos_a - pad_y * sin_a
                rotated_y = pad_x * sin_a + pad_y * cos_a
                pad_x, pad_y = rotated_x, rotated_y
            pos = Point(comp.position.x + pad_x,
                        comp.position.y + pad_y)
            sx = float(size_node[1]) if len(size_node) > 1 else 1.0
            sy = float(size_node[2]) if len(size_node) > 2 else sx
            net_id = int(_val(pad_node, "net", 0) or 0)
            layers_node = _find(pad_node, "layers")
            layers = []
            if layers_node:
                layers = [str(l) for l in layers_node[1:]
                          if isinstance(l, str)]
            return Pad(
                position=pos, size_x=sx, size_y=sy,
                pad_type=str(pad_type), shape=str(shape),
                layers=layers, net=net_id,
                net_name=board.nets.get(net_id, ""),
                component_ref=comp.reference
            )
        except Exception:
            return None

    def _parse_zones(self, root: list, board: PCBBoard):
        for zone_node in _find_all(root, "zone"):
            net_id = int(_val(zone_node, "net", 0) or 0)
            net_name = _val(zone_node, "net_name", "") or ""
            layer = _val(zone_node, "layer", "F.Cu")

            polygon = []
            poly_node = _find(zone_node, "polygon")
            if poly_node:
                pts_node = _find(poly_node, "pts")
                if pts_node:
                    for pt in _find_all(pts_node, "xy"):
                        polygon.append(_pt(pt))

            if polygon:
                board.zones.append(Zone(
                    layer=str(layer), net=net_id,
                    net_name=str(net_name), polygon=polygon
                ))

    def _compute_board_size(self, tree: list, board: PCBBoard):
        """Estimate board bounding box from edge cuts or all traces."""
        edge_pts: list[Point] = []
        for t in board.traces:
            if "Edge.Cuts" in t.layer:
                edge_pts.extend([t.start, t.end])

        # Also check gr_line on Edge.Cuts (KiCad 6+)
        for node in _find_all(tree, 'gr_line'):
            layer = _val(node, 'layer')
            if layer and 'Edge.Cuts' in layer:
                start = _find(node, 'start')
                end = _find(node, 'end')
                if start and end:
                    edge_pts.extend([_pt(start), _pt(end)])

        all_x = [p.x for p in edge_pts]
        all_y = [p.y for p in edge_pts]

        if not all_x:  # fallback: use all geometry
            for t in board.traces:
                all_x += [t.start.x, t.end.x]
                all_y += [t.start.y, t.end.y]
            for v in board.vias:
                all_x.append(v.position.x)
                all_y.append(v.position.y)
            for p in board.pads:
                all_x.append(p.position.x)
                all_y.append(p.position.y)

        if all_x and all_y:
            board.origin = Point(min(all_x), min(all_y))
            board.width = max(all_x) - min(all_x)
            board.height = max(all_y) - min(all_y)


# ─────────────────────────────────────────────────────────────
# Demo / synthetic board generator for testing without a file
# ─────────────────────────────────────────────────────────────

def create_demo_board() -> PCBBoard:
    """Create a realistic synthetic PCB for demonstration purposes."""
    import random
    rng = random.Random(42)

    board = PCBBoard(file_path="<demo>")
    board.title = "Demo ESP32 RF Board"
    board.width = 100.0
    board.height = 80.0
    board.origin = Point(0, 0)
    board.layers = ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]

    # Nets
    board.nets = {
        0: "",
        1: "GND",
        2: "VCC_3V3",
        3: "VCC_5V",
        4: "RF_ANT",
        5: "MOSI",
        6: "MISO",
        7: "SCK",
        8: "CS",
        9: "TX",
        10: "RX",
        11: "I2C_SCL",
        12: "I2C_SDA",
    }

    # Traces (mix of signal types)
    trace_defs = [
        # Long RF trace (antenna-like)
        (Point(50, 20), Point(87, 20), 0.2, "F.Cu", 4),
        # Power trace (wide)
        (Point(5, 5),  Point(95, 5),  1.5, "F.Cu", 2),
        (Point(5, 75), Point(95, 75), 1.5, "B.Cu", 3),
        # High-speed traces
        (Point(20, 40), Point(60, 40), 0.15, "F.Cu", 5),
        (Point(20, 42), Point(60, 42), 0.15, "F.Cu", 6),
        (Point(20, 44), Point(60, 44), 0.15, "F.Cu", 7),
        (Point(20, 46), Point(60, 46), 0.15, "F.Cu", 8),
        # UART crossing split plane
        (Point(10, 60), Point(90, 60), 0.2, "F.Cu", 9),
        (Point(10, 63), Point(90, 63), 0.2, "F.Cu", 10),
        # Short I2C
        (Point(30, 30), Point(40, 30), 0.2, "F.Cu", 11),
        (Point(30, 32), Point(40, 32), 0.2, "F.Cu", 12),
        # GND trace (short return path issue)
        (Point(70, 20), Point(70, 50), 0.5, "F.Cu", 1),
        # Another long trace
        (Point(5, 50), Point(95, 50), 0.3, "B.Cu", 5),
        # Parallel traces (crosstalk risk)
        (Point(75, 30), Point(95, 30), 0.2, "F.Cu", 9),
        (Point(75, 31), Point(95, 31), 0.2, "F.Cu", 10),
        (Point(75, 32), Point(95, 32), 0.2, "F.Cu", 11),
    ]

    for s, e, w, lyr, net in trace_defs:
        board.traces.append(Trace(
            start=s, end=e, width=w, layer=lyr,
            net=net, net_name=board.nets.get(net, "")
        ))

    # Add random traces
    for _ in range(30):
        x1, y1 = rng.uniform(5, 95), rng.uniform(5, 75)
        x2 = x1 + rng.uniform(-15, 15)
        y2 = y1 + rng.uniform(-15, 15)
        x2 = max(2, min(98, x2))
        y2 = max(2, min(78, y2))
        net = rng.randint(1, 12)
        lyr = rng.choice(["F.Cu", "B.Cu"])
        board.traces.append(Trace(
            start=Point(x1, y1), end=Point(x2, y2),
            width=rng.choice([0.1, 0.15, 0.2, 0.3]),
            layer=lyr, net=net,
            net_name=board.nets.get(net, "")
        ))

    # Vias
    via_positions = [
        (30, 40), (30, 42), (30, 44), (30, 46),
        (60, 40), (60, 42), (60, 44), (60, 46),
        (50, 30), (50, 50), (20, 60), (80, 60),
    ]
    for x, y in via_positions:
        net = rng.randint(1, 12)
        board.vias.append(Via(
            position=Point(x, y), drill=0.3, size=0.6,
            layers=["F.Cu", "B.Cu"], net=net,
            net_name=board.nets.get(net, "")
        ))

    # Ground plane (B.Cu)
    gnd_polygon = [
        Point(2, 2), Point(98, 2), Point(98, 78), Point(2, 78)
    ]
    board.zones.append(Zone(
        layer="B.Cu", net=1, net_name="GND",
        polygon=gnd_polygon
    ))

    # Partial ground plane on F.Cu (with gap = discontinuity)
    board.zones.append(Zone(
        layer="F.Cu", net=1, net_name="GND",
        polygon=[Point(2, 2), Point(45, 2),
                 Point(45, 78), Point(2, 78)]
    ))
    board.zones.append(Zone(
        layer="F.Cu", net=1, net_name="GND",
        polygon=[Point(55, 2), Point(98, 2),
                 Point(98, 78), Point(55, 78)]
    ))

    # Pads
    pad_defs = [
        (Point(50, 20), 1.0, 1.0, "smd", 4, "U1"),    # RF antenna pad
        (Point(20, 40), 0.8, 0.8, "thru_hole", 5, "U2"),
        (Point(60, 40), 0.8, 0.8, "thru_hole", 6, "U2"),
        (Point(30, 30), 0.5, 0.5, "smd", 11, "U3"),
        (Point(70, 60), 1.5, 1.5, "thru_hole", 2, "C1"),  # decap
        (Point(72, 60), 1.5, 1.5, "thru_hole", 1, "C1"),
    ]
    for pos, sx, sy, ptype, net, ref in pad_defs:
        board.pads.append(Pad(
            position=pos, size_x=sx, size_y=sy,
            pad_type=ptype, shape="rect",
            layers=["F.Cu"], net=net,
            net_name=board.nets.get(net, ""),
            component_ref=ref
        ))

    # Components
    board.components = [
        Component("U1", "ESP32-WROOM", Point(50, 35), "F.Cu"),
        Component("U2", "STM32F4", Point(40, 43), "F.Cu"),
        Component("U3", "AMS1117", Point(15, 10), "F.Cu"),
        Component("C1", "100nF", Point(71, 60), "F.Cu"),
        Component("C2", "10uF", Point(80, 10), "F.Cu"),
        Component("R1", "10k", Point(35, 55), "F.Cu"),
        Component("R2", "10k", Point(38, 55), "F.Cu"),
        Component("J1", "SMA_RF", Point(90, 20), "F.Cu"),
    ]

    return board
