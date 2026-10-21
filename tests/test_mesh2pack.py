"""Fork feature: the tools that shape furniture out of 3D models (see FORK.md).

tools/mesh2pack.py turns a model into the boxes and cylinders a pack item is made of, and
tools/sh3d_import.py reads a Sweet Home 3D library. Both only produce data for packs.py, so
these tests pin what matters: that a shape comes out as the solid it stands for, that an item
passes the real ITEM_SCHEMA, and that a catalogue entry becomes the right kind of item.

numpy and scipy are not part of requirements_test.txt, so the tests that need them skip when
they are missing; the ones that do not need them always run.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import pytest

from custom_components.neonplan3d import packs

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def _tool(name: str):
    """Load a tool module by path (tools/ is not a package)."""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location(f"fp3d_{name}", TOOLS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- colours: no model data needed ----------------------------------------


def test_material_name_beats_colour() -> None:
    """A part called "seat" is a cushion whatever colour the model gave it."""
    m2p = _tool("mesh2pack")
    assert m2p.role_of((0.1, 0.9, 0.2), "seat") == "cushion"
    assert m2p.role_of((0.9, 0.9, 0.9), "wooden_leg") == "wood"
    assert m2p.role_of((0.5, 0.5, 0.5), "chrome_frame") == "metal"


def test_green_is_not_a_plant_unless_asked() -> None:
    """Whoever built the model picked its colours freely: a green armchair is not a shrub."""
    m2p = _tool("mesh2pack")
    assert m2p.role_of((0.33, 0.76, 0.29)) != "plant"
    assert m2p.role_of((0.33, 0.76, 0.29), plantish=True) == "plant"


def test_every_role_is_one_the_schema_knows() -> None:
    """Whatever colour a model carries, the role must pass _COLOR of PART_SCHEMA."""
    m2p = _tool("mesh2pack")
    probes = [(0, 0, 0), (1, 1, 1), (0.5, 0.5, 0.5), (0.8, 0.1, 0.1), (0.1, 0.1, 0.8), (0.6, 0.4, 0.2)]
    for rgb in probes:
        for alpha in (1.0, 0.3):
            role = m2p.role_of(rgb, alpha=alpha)
            packs.PART_SCHEMA({"shape": "box", "x": 0, "z": 0, "w": 1, "d": 1, "y": 0, "h": 1, "color": role})


def test_roles_and_palette_agree() -> None:
    """Every role the tool can produce has a colour for the preview, and none is invented."""
    m2p = _tool("mesh2pack")
    hinted = {role for _, role in m2p.NAME_HINTS}
    assert hinted <= set(m2p.ROLE_RGB)
    for role in m2p.ROLE_RGB:
        packs.PART_SCHEMA({"shape": "box", "x": 0, "z": 0, "w": 1, "d": 1, "y": 0, "h": 1, "color": role})


# --- the shapes: these need numpy -----------------------------------------


def test_a_hollow_shell_becomes_solid() -> None:
    """Models of furniture are hollow. The inside has to come out solid, or every part is a sheet."""
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    shell = np.zeros((10, 10, 10), dtype=bool)
    shell[0, :, :] = shell[-1, :, :] = True
    shell[:, 0, :] = shell[:, -1, :] = True
    shell[:, :, 0] = shell[:, :, -1] = True
    solid = m2p.solidify(shell)
    assert solid.all()


def test_an_open_bay_stays_open() -> None:
    """A shelf is open at the front, and filling it up would make it a cupboard."""
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    shell = np.zeros((10, 10, 10), dtype=bool)
    shell[:, 0, :] = shell[:, -1, :] = True  # bottom and top shelf
    shell[0, :, :] = shell[-1, :, :] = True  # the two sides
    shell[:, :, 0] = True  # the back, nothing at the front
    solid = m2p.solidify(shell)
    assert not solid[5, 5, 8], "the bay in front of the back panel must stay empty"


def test_a_box_is_covered_by_one_part() -> None:
    """A solid block needs one box, not a staircase of slivers."""
    pytest.importorskip("numpy")
    pytest.importorskip("scipy")
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    solid = np.zeros((12, 12, 12), dtype=bool)
    solid[2:10, 2:10, 2:10] = True
    boxes = m2p.cover(solid, 20)
    assert len(boxes) == 1
    assert boxes[0] == [2, 2, 2, 10, 10, 10]


def test_a_part_grows_in_every_direction() -> None:
    """The seat of a chair is a cushion, not a sheet of paper: a box must not eat one axis first."""
    pytest.importorskip("scipy")
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    solid = np.zeros((16, 16, 16), dtype=bool)
    solid[3:13, 3:13, 3:13] = True
    box = m2p.cover(solid, 4)[0]
    sides = (box[3] - box[0], box[4] - box[1], box[5] - box[2])
    assert min(sides) >= 8, f"the part came out flat: {sides}"


def test_quality_sees_a_bad_cover() -> None:
    """The likeness measure has to tell a fitting part from one that misses the model."""
    pytest.importorskip("scipy")
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    solid = np.zeros((10, 10, 10), dtype=bool)
    solid[0:5, 0:10, 0:10] = True
    good = [{"shape": "box", "x": -0.25, "z": 0, "w": 0.5, "d": 1, "y": 0, "h": 1, "color": "body"}]
    bad = [{"shape": "box", "x": 0.4, "z": 0, "w": 0.2, "d": 0.2, "y": 0, "h": 0.2, "color": "body"}]
    assert m2p.quality(good, solid) > 0.9
    assert m2p.quality(bad, solid) < 0.2


def test_parts_fit_the_schema_and_the_item_is_valid(tmp_path: Path) -> None:
    """A built item must pass the integration's own schema, or the whole pack is refused."""
    pytest.importorskip("scipy")
    trimesh = pytest.importorskip("trimesh")
    m2p = _tool("mesh2pack")
    path = tmp_path / "box.ply"
    trimesh.creation.box(extents=(1.0, 0.5, 0.8)).export(path)
    item = m2p.build_item(path, "block", {"de": "Block", "en": "Block"}, size=(1.0, 0.8, 0.5))
    packs.ITEM_SCHEMA(item)
    assert 1 <= len(item["parts"]) <= 60
    assert item["size"] == [1.0, 0.8, 0.5]


def test_share_out_gives_every_block_a_part() -> None:
    """A small block still gets one part, so the legs of a chair do not vanish."""
    pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    shares = m2p.share_out([1000, 10, 10, 10, 10], 12)
    assert len(shares) == 5
    assert min(shares) >= 1
    assert sum(shares) == 12
    assert shares[0] == max(shares)


def test_share_out_never_promises_more_than_the_budget() -> None:
    """More blocks than parts: the budget still holds, the smallest blocks drop out."""
    pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    shares = m2p.share_out([10] * 20, 5)
    assert sum(shares) == 5


# --- the catalogue ---------------------------------------------------------


def test_a_lamp_becomes_a_lamp() -> None:
    """The catalogue's category decides the light kind, mount and whether it draws power."""
    sh3d = _tool("sh3d_import")
    out = sh3d.traits({"category": "Lights", "name": "Ceiling lamp", "_names": {"de": "Deckenlampe"}, "height": "30"})
    assert out["light"] == "ceiling"
    assert out["mount"] == "ceiling"
    assert out["electric"] is True


def test_a_wall_lamp_hangs_at_its_height() -> None:
    """A piece the catalogue puts above the floor belongs on the wall, at that height."""
    sh3d = _tool("sh3d_import")
    out = sh3d.traits(
        {"category": "Lights", "name": "Wall light", "_names": {"en": "Wall light"}, "height": "25", "elevation": "180"}
    )
    assert out["light"] == "wall"
    assert out["mount"] == "wall"
    assert out["wall_y"] == pytest.approx(1.8)


def test_stairs_cut_a_hole_and_cars_park() -> None:
    """Stairs and vehicles carry the flags NeonPlan 3D needs to place them."""
    sh3d = _tool("sh3d_import")
    assert sh3d.traits({"category": "Staircases", "name": "Stairs", "_names": {}, "height": "250"})["hole"] is True
    assert sh3d.traits({"category": "Vehicles", "name": "Car", "_names": {}, "height": "150"})["vehicle"] is True


def test_a_table_carries_things() -> None:
    """A piece whose catalogue entry drops things on its top is a surface."""
    sh3d = _tool("sh3d_import")
    out = sh3d.traits(
        {"category": "Living room", "name": "Table", "_names": {}, "height": "75", "dropOnTopElevation": "75"}
    )
    assert out.get("surface") is True


def test_traits_pass_the_item_schema() -> None:
    """Whatever the catalogue says, the fields have to be ones ITEM_SCHEMA accepts."""
    sh3d = _tool("sh3d_import")
    entries = [
        {"category": "Lights", "name": "Pendant", "_names": {}, "height": "40", "elevation": "200"},
        {"category": "Staircases", "name": "Stairs", "_names": {}, "height": "250"},
        {"category": "Kitchen", "name": "Fridge", "_names": {}, "height": "180", "dropOnTopElevation": "180"},
        {"category": "Miscellaneous", "name": "Mirror", "_names": {}, "height": "60", "elevation": "120"},
    ]
    part = {"shape": "box", "x": 0, "z": 0, "w": 1, "d": 1, "y": 0, "h": 1, "color": "body"}
    for entry in entries:
        item = {"id": "x", "name": {"en": "X"}, "size": [1, 1, 1], "parts": [part], **sh3d.traits(entry)}
        packs.ITEM_SCHEMA(item)


def test_doors_and_windows_are_left_to_neonplan() -> None:
    """NeonPlan 3D draws doors and windows itself, as part of the wall."""
    sh3d = _tool("sh3d_import")
    assert "Doors and windows" in sh3d.SKIP_CATEGORIES


def test_item_ids_stay_unique_and_legal() -> None:
    """Two pieces of the same name must not collide, and an id has to match the schema."""
    sh3d = _tool("sh3d_import")
    used: set[str] = set()
    ids = [sh3d.slug(name, used) for name in ("Chair", "Chair", "Chair", "Ärmchair!", "")]
    assert len(set(ids)) == len(ids)
    part = {"shape": "box", "x": 0, "z": 0, "w": 1, "d": 1, "y": 0, "h": 1, "color": "body"}
    for item_id in ids:
        packs.ITEM_SCHEMA({"id": item_id, "name": {"en": "X"}, "size": [1, 1, 1], "parts": [part]})


# --- a loft's top: the schema's words, not the tool's ----------------------


def test_a_loft_top_is_a_span_of_the_item_not_a_ratio() -> None:
    """PART_SCHEMA reads "tw"/"td" like "w"/"d": the top rectangle as a span of the item.

    A tool that writes the ratio there ("half of what the part is wide") makes NeonPlan draw a
    top half the *whole item* wide - on a chair leg ten times too much. The schema cannot catch
    it, both are plain fractions, so it has to be pinned here. A loft may also widen upwards,
    which a ratio capped at 1 could never say.
    """
    pytest.importorskip("scipy")
    pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    narrow = {
        "shape": "loft",
        "x": 0.0,
        "z": 0.0,
        "w": 0.8,
        "d": 0.8,
        "y": 0.0,
        "h": 1.0,
        "tw": 0.2,
        "td": 0.2,
        "color": "body",
    }
    wide = {
        "shape": "loft",
        "x": 0.0,
        "z": 0.0,
        "w": 0.2,
        "d": 0.2,
        "y": 0.0,
        "h": 1.0,
        "tw": 0.8,
        "td": 0.8,
        "color": "body",
    }
    for part, expected in ((narrow, 0.2), (wide, 0.8)):
        packs.PART_SCHEMA(part)
        drawn = m2p.parts_solid([part], (40, 16, 40))
        top = drawn[:, -1, :]
        width = float(top.any(axis=1).sum()) / 40
        assert abs(width - expected) <= 0.08, f"top drawn {width:.2f} wide, the schema says {expected}"


def test_a_loft_top_sits_where_the_item_says() -> None:
    """ "tx" is a centre in the item like "x", not a shift away from the part's own centre."""
    pytest.importorskip("scipy")
    pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    part = {
        "shape": "loft",
        "x": -0.2,
        "z": 0.0,
        "w": 0.3,
        "d": 0.3,
        "y": 0.0,
        "h": 1.0,
        "tw": 0.3,
        "td": 0.3,
        "tx": 0.2,
        "color": "body",
    }
    packs.PART_SCHEMA(part)
    drawn = m2p.parts_solid([part], (40, 16, 40))
    hit = drawn[:, -1, :].any(axis=1).nonzero()[0]
    centre = (float(hit[0]) + float(hit[-1]) + 1) / 2 / 40 - 0.5
    assert abs(centre - 0.2) <= 0.06, f"top centred at {centre:.2f}, the schema says 0.2"


def test_a_loft_is_written_in_the_items_fractions() -> None:
    """The other side: shape_of measures against the part's own box, the pack wants the item.

    A leg a quarter of the item wide that ends at a third of itself is 0.08 of the item at the
    top, not 0.33 - and its top centre is the part's centre plus a third of the part, not plus a
    third of the item.
    """
    m2p = _tool("mesh2pack")
    fields = m2p.loft_fields({"tw": 1 / 3, "td": 1 / 3, "tx": 0.5}, x=0.25, z=0.0, w=0.24, d=0.24)
    assert fields["tw"] == pytest.approx(0.08, abs=0.005)
    assert fields["td"] == pytest.approx(0.08, abs=0.005)
    assert fields["tx"] == pytest.approx(0.25 + 0.5 * 0.24, abs=0.005)
    assert "tz" not in fields  # unmoved: the schema falls back to the part's own centre
    packs.PART_SCHEMA(
        {"shape": "loft", "x": 0.25, "z": 0.0, "w": 0.24, "d": 0.24, "y": 0.0, "h": 0.5, "color": "wood", **fields}
    )


def test_the_voxel_is_a_length_not_a_count() -> None:
    """A big piece has to be rastered as finely as a small one, or its detail is gone.

    Cells per longest side made the cell grow with the piece: at 24 a 3.5 m staircase got 15 cm
    cells while its steps are 17 cm high, so no two steps came out the same and the item read as
    a heap. The cell is a length now. A chair was already finer than that and must not change,
    and a very large piece stops at MAX_GRID so the grid still fits in memory.
    """
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")

    stairs = m2p.voxels(np.array([0.9, 3.5, 3.4]), grid=24, cell=0.045)
    assert max(3.5 / stairs[1], 3.4 / stairs[2]) <= 0.06, f"stairs rastered at {3.5 / stairs[1]:.3f} m"

    chair = m2p.voxels(np.array([0.45, 0.9, 0.5]), grid=24, cell=0.045)
    assert max(chair) == 24, f"a chair must keep what it had, got {chair}"

    garden = m2p.voxels(np.array([8.0, 1.5, 8.0]), grid=24, cell=0.045)
    assert max(garden) == m2p.MAX_GRID
    assert min(garden) >= 3


# --- a turned part: the schema's "rot" ------------------------------------


def test_a_turned_part_is_measured_turned() -> None:
    """PART_SCHEMA turns a part around its own centre with "rot"; the measure has to follow.

    Without it every step of a spiral staircase counts as a miss, and the likeness measure
    punishes the very item that reads best.
    """
    pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    plank = {"shape": "box", "x": 0.0, "z": 0.0, "w": 0.8, "d": 0.2, "y": 0.0, "h": 1.0, "color": "body"}
    turned = {**plank, "rot": 90}
    packs.PART_SCHEMA(turned)
    drawn = m2p.parts_solid([turned], (40, 8, 40))
    plan = drawn[:, 4, :]
    across = float(plan.any(axis=1).sum()) / 40
    deep = float(plan.any(axis=0).sum()) / 40
    assert abs(across - 0.2) <= 0.06, f"the turned plank came out {across:.2f} across, want 0.2"
    assert abs(deep - 0.8) <= 0.06, f"the turned plank came out {deep:.2f} deep, want 0.8"


def test_a_part_turned_by_a_half_quarter_lies_on_its_diagonal() -> None:
    """At 45 degrees a plank is neither across nor deep: it reaches into both corners."""
    pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    part = {"shape": "box", "x": 0.0, "z": 0.0, "w": 0.7, "d": 0.14, "y": 0.0, "h": 1.0, "color": "body", "rot": 45}
    packs.PART_SCHEMA(part)
    plan = m2p.parts_solid([part], (40, 8, 40))[:, 4, :]
    corner = 0.7 / 2 * 0.7071 + 0.14 / 2 * 0.7071  # half the diagonal reach, both ways
    across = float(plan.any(axis=1).sum()) / 40
    assert abs(across - 2 * corner) <= 0.08, f"reaches {across:.2f} across, want {2 * corner:.2f}"
    # and it really is a diagonal, not a square: the front-left corner of the plan stays empty
    assert not plan[:6, :6].any(), "a part on its diagonal must leave the corners free"


def test_the_preview_draws_a_turned_part_turned() -> None:
    """A plank turned a quarter is the same picture as one built the other way round.

    The preview is how the shaping is judged by eye. A "rot" it ignored would hide exactly what
    it is there to show.
    """
    np = pytest.importorskip("numpy")
    pytest.importorskip("PIL")
    m2p = _tool("mesh2pack")

    def item(part: dict[str, object]) -> dict[str, object]:
        return {"id": "x", "name": {"en": "X"}, "size": [1.0, 1.0, 0.4], "parts": [part]}

    turned = item({"shape": "box", "x": 0, "z": 0, "w": 0.8, "d": 0.2, "y": 0, "h": 1, "color": "body", "rot": 90})
    built = item({"shape": "box", "x": 0, "z": 0, "w": 0.2, "d": 0.8, "y": 0, "h": 1, "color": "body"})
    drawn = np.asarray(m2p.render_parts(turned, 120), dtype=int)
    want = np.asarray(m2p.render_parts(built, 120), dtype=int)
    off = float((np.abs(drawn - want) > 1).mean())
    assert off < 0.005, f"the preview ignored rot: {off:.1%} of the picture differs"


# --- finding the turn of a block -----------------------------------------


def _turned_plan(deg: float, half_long: float, half_short: float, size: int = 60):
    """A plan (x, z) holding one rectangle turned by `deg` around the middle."""
    np = pytest.importorskip("numpy")
    xs, zs = np.mgrid[0:size, 0:size]
    angle = np.radians(deg)
    ux, uz = xs - (size - 1) / 2, zs - (size - 1) / 2
    long_way = ux * np.cos(angle) + uz * np.sin(angle)
    short_way = -ux * np.sin(angle) + uz * np.cos(angle)
    return (np.abs(long_way) <= half_long) & (np.abs(short_way) <= half_short)


def test_a_turned_plank_gives_away_its_angle() -> None:
    """A step of a spiral staircase lies across the grid: the cover has to find its line.

    Upright boxes can only stair-case along such a plank, which is why a spiral staircase came
    out as a heap. PART_SCHEMA has "rot" for it, so the angle has to be measured first.
    """
    m2p = _tool("mesh2pack")
    for deg in (20.0, 35.0, -30.0):
        found, gain = m2p.main_angle(_turned_plan(deg, 20, 4))
        assert abs(found - deg) <= 5, f"plank at {deg}° read as {found}°"
        assert gain > 1.5, f"plank at {deg}°: turning it saves nothing ({gain:.2f})"


def test_a_square_block_is_left_alone() -> None:
    """A cupboard stands square to the room. Inventing an angle would only tilt it."""
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    plan = np.zeros((40, 40), dtype=bool)
    plan[8:32, 12:28] = True
    found, gain = m2p.main_angle(plan)
    assert gain < 1.1, f"an upright block was offered a turn of {found}° (gain {gain:.2f})"


def test_a_round_plan_claims_no_angle() -> None:
    """A round table top fits every angle equally: turning it buys nothing, so it must not."""
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    xs, zs = np.mgrid[0:40, 0:40]
    plan = ((xs - 19.5) ** 2 + (zs - 19.5) ** 2) <= 18**2
    _, gain = m2p.main_angle(plan)
    assert gain < 1.1, f"a circle was read as turned (gain {gain:.2f})"


def test_the_angle_is_the_shortest_way_round() -> None:
    """A plank along z is the same as one along x turned a quarter: say the smaller turn.

    A step turned by 80° and one turned by -10° draw the same box; writing the large number
    would make the plan symbol and the outline jump for no reason.
    """
    m2p = _tool("mesh2pack")
    found, _ = m2p.main_angle(_turned_plan(80.0, 20, 4))
    assert -45 <= found <= 45, f"angle {found}° is not the shortest way round"
    assert abs(found - -10.0) <= 5, f"80° should read as -10°, got {found}°"


# --- covering a turned block ----------------------------------------------


def test_turning_a_block_makes_it_stand_square() -> None:
    """To cover a turned block with one box, the cover first puts the block upright."""
    pytest.importorskip("scipy")
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    plan = _turned_plan(30.0, 20, 4)
    solid = np.repeat(plan[:, None, :], 5, axis=1)
    straight = m2p.upright(solid, 30.0)
    hit = straight.any(axis=1)
    across = int(hit.any(axis=1).sum())
    deep = int(hit.any(axis=0).sum())
    assert abs(across - 41) <= 4, f"the plank is {across} cells long after turning, want 41"
    assert abs(deep - 9) <= 4, f"the plank is {deep} cells deep after turning, want 9"


def test_a_box_found_in_the_turned_grid_lands_where_the_block_is() -> None:
    """The turned grid is bigger and shifted; a box read from it has to come back in place."""
    pytest.importorskip("scipy")
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    # a small block well off centre, so a wrong centre cannot pass as right
    plan = np.zeros((60, 60), dtype=bool)
    plan[40:50, 10:16] = True
    solid = np.repeat(plan[:, None, :], 5, axis=1)
    straight = m2p.upright(solid, 25.0)
    box = m2p.cover(straight, 1)[0]
    x, z = m2p.turn_back(box, straight.shape, solid.shape, 25.0)
    assert abs(x - (44.5 / 60 - 0.5)) <= 0.04, f"came back at x={x:.3f}, want {44.5 / 60 - 0.5:.3f}"
    assert abs(z - (12.5 / 60 - 0.5)) <= 0.04, f"came back at z={z:.3f}, want {12.5 / 60 - 0.5:.3f}"


def test_a_tread_lying_at_an_angle_is_one_turned_part(tmp_path: Path) -> None:
    """The point of it all: a spiral step is one part, not a flight of upright slivers.

    Upright boxes can only stair-case along a turned plank, which is what made every spiral
    staircase in the catalogue read as a heap of blocks.
    """
    pytest.importorskip("scipy")
    trimesh = pytest.importorskip("trimesh")
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    tread = trimesh.creation.box(extents=(0.9, 0.04, 0.26))
    tread.apply_transform(trimesh.transformations.rotation_matrix(np.radians(30), [0, 1, 0]))
    path = tmp_path / "tread.ply"
    tread.export(path)
    report: dict[str, object] = {}
    item = m2p.build_item(path, "tread", {"en": "Tread"}, report=report)
    packs.ITEM_SCHEMA(item)
    turned = [p for p in item["parts"] if p.get("rot")]
    assert turned, f"the tread was not read as turned: {item['parts']}"
    assert len(item["parts"]) <= 4, f"the tread fell apart into {len(item['parts'])} slivers"
    assert report["iou"] > 0.8, f"the turned cover misses the block (iou {report['iou']})"


# --- every part its own angle ---------------------------------------------


def test_two_treads_at_different_angles_each_get_their_own() -> None:
    """A spiral staircase is one block: its steps hang together on the newel.

    So an angle for the whole block is no use - the block's own plan is a circle and says
    nothing. Each step has to get the angle of the step it is, or they come out as upright
    stair-cased slivers however finely the model is rastered.
    """
    pytest.importorskip("scipy")
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    solid = np.zeros((64, 8, 64), dtype=bool)
    solid[:, :4, :] = np.repeat(_turned_plan(55.0, 22, 3, 64)[:, None, :], 4, axis=1)
    solid[:, 4:, :] = np.repeat(_turned_plan(20.0, 22, 3, 64)[:, None, :], 4, axis=1)
    found = m2p.turned_cover(solid, 6)
    assert len(found) <= 4, f"the two treads fell into {len(found)} parts"
    angles = sorted(round(box["rot"]) for box in found)
    assert any(abs(a - 55) <= 6 for a in angles), f"the lower tread was lost: {angles}"
    assert any(abs(a - 20) <= 6 for a in angles), f"the upper tread was lost: {angles}"


def test_a_tread_is_one_box_not_a_staircase_of_slivers() -> None:
    """The whole point: a step lying across the grid is one turned box."""
    pytest.importorskip("scipy")
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    solid = np.repeat(_turned_plan(40.0, 18, 3, 50)[:, None, :], 4, axis=1)
    found = m2p.turned_cover(solid, 10)
    assert len(found) == 1, f"the tread came out in {len(found)} parts"
    box = found[0]
    assert abs(box["rot"] - 40) <= 6, f"read as {box['rot']}°, want 40°"
    assert abs(box["w"] - 37) <= 4 and abs(box["d"] - 7) <= 4, f"box is {box['w']:.0f}x{box['d']:.0f} cells"


def test_an_upright_block_keeps_its_corners_square() -> None:
    """A cupboard read layer by layer must not come out tilted by a degree or two."""
    pytest.importorskip("scipy")
    np = pytest.importorskip("numpy")
    m2p = _tool("mesh2pack")
    solid = np.zeros((20, 10, 16), dtype=bool)
    solid[4:16, :, 3:13] = True
    found = m2p.turned_cover(solid, 6)
    assert len(found) == 1, f"a plain block came out in {len(found)} parts"
    turn = found[0]["rot"] % 90
    assert min(turn, 90 - turn) < 1e-6, f"an upright block was tilted by {found[0]['rot']}°"
