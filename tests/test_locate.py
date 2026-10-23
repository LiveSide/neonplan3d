"""Locating: settings over the websocket, a room sensor per device, presence sensors confirming a room."""

from __future__ import annotations

import time

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.neonplan3d.const import DOMAIN
from custom_components.neonplan3d.locate.engine import Fingerprints
from custom_components.neonplan3d.locate.service import DATA_LOCATE, SIGNAL_LOCATE, LocateService

ROOMS = [
    {"id": "kitchen", "name": "Kitchen", "floor": "Ground", "area_id": "kitchen"},
    {"id": "hall", "name": "Hall", "floor": "Ground", "area_id": "hall"},
    {"id": "living", "name": "Living", "floor": "Ground", "area_id": None},
]
WATCH = {"id": "irk_watch", "name": "Watch", "kind": "irk", "key": "00112233445566778899aabbccddeeff", "person": None}


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_without_bluetooth(hass: HomeAssistant, hass_ws_client) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": "neonplan3d/locate/config"})
    res = await client.receive_json()
    assert res["success"]
    assert res["result"]["enabled"] is False
    assert res["result"]["bluetooth"] is False
    assert res["result"]["devices"] == []


async def test_a_device_gets_a_room_sensor(hass: HomeAssistant, hass_ws_client, hass_storage) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "neonplan3d/locate/configure",
            "devices": [WATCH],
            "rooms": ROOMS,
            "doors": [["kitchen", "hall"], ["hall", "living"]],
            "scanner_rooms": {"AA:BB:CC:DD:EE:01": "kitchen"},
        }
    )
    res = await client.receive_json()
    assert res["success"], res
    assert [d["id"] for d in res["result"]["devices"]] == ["irk_watch"]
    await hass.async_block_till_done()

    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_locate_irk_watch")
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "unknown"

    # the service found the watch in the kitchen: the sensor says so
    service: LocateService = hass.data[DATA_LOCATE]
    service.state["irk_watch"] = {
        "room": "kitchen",
        "room_name": "Kitchen",
        "floor": "Ground",
        "area_id": "kitchen",
        "probability": 0.93,
        "since": time.time(),
        "last_seen": time.time(),
    }
    async_dispatcher_send(hass, SIGNAL_LOCATE)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == "Kitchen"
    assert state.attributes["room_id"] == "kitchen"
    assert state.attributes["neonplan_locate"] is True

    # settings and devices are kept (store), the room samples are not part of the reply
    await hass.async_block_till_done()


async def test_admin_only_commands(hass: HomeAssistant, hass_ws_client, hass_read_only_access_token) -> None:
    await _setup(hass)
    client = await hass_ws_client(hass, hass_read_only_access_token)
    await client.send_json_auto_id({"type": "neonplan3d/locate/configure", "enabled": True})
    res = await client.receive_json()
    assert not res["success"]
    assert res["error"]["code"] == "unauthorized"
    # everyone may watch where people are (unless "admins only")
    await client.send_json_auto_id({"type": "neonplan3d/locate/subscribe"})
    res = await client.receive_json()
    assert res["success"]


async def test_presence_sensor_maps_to_the_plan_room(hass: HomeAssistant) -> None:
    await _setup(hass)
    service: LocateService = hass.data[DATA_LOCATE]
    await service.async_configure({"devices": [WATCH], "rooms": ROOMS, "doors": [["kitchen", "hall"]]})
    area = ar.async_get(hass).async_create("Hall")
    entry = er.async_get(hass).async_get_or_create("binary_sensor", "test", "motion_hall")
    er.async_get(hass).async_update_entity(entry.entity_id, area_id=area.id)
    # the plan room is linked by the area id
    service.rooms = [{**r, "area_id": area.id} if r["id"] == "hall" else r for r in ROOMS]
    service._sensor_rooms = {}
    assert service._sensor_room(entry.entity_id) == "hall"
    assert service._sensor_room("binary_sensor.elsewhere") is None


async def test_unload_stops_the_service(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert DATA_LOCATE in hass.data
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert DATA_LOCATE not in hass.data


async def test_spoken_answers_come_from_the_service(hass: HomeAssistant) -> None:
    await _setup(hass)
    service: LocateService = hass.data[DATA_LOCATE]
    keys = {**WATCH, "id": "mac_tag", "name": "Keys", "kind": "mac", "key": "C0:11:22:33:44:55"}
    await service.async_configure({"devices": [WATCH, keys], "rooms": ROOMS})
    now = time.time()
    kitchen = {"room": "kitchen", "room_name": "Kitchen", "probability": 0.9}
    service.state["irk_watch"] = {**kitchen, "since": now, "last_seen": now}

    async def ask(text: str) -> dict:
        return await hass.services.async_call(DOMAIN, "ask", {"text": text}, blocking=True, return_response=True)

    res = await ask("Where is my watch?")
    assert res == {"answered": True, "answer": "Watch is in the Kitchen.", "screen_open": False}
    assert (await ask("where are the keys"))["answer"] == "I can't hear Keys right now."
    assert (await ask("who is home"))["answer"] == "At home: Watch (Kitchen)."
    assert (await ask("ring my watch"))["answer"] == "No app to ring is set for Watch."
    # anything else still goes to the screens (none open here)
    assert (await ask("show the kitchen"))["screen_open"] is False


async def test_removing_a_device_removes_its_sensor(hass: HomeAssistant) -> None:
    await _setup(hass)
    service: LocateService = hass.data[DATA_LOCATE]
    await service.async_configure({"devices": [WATCH], "rooms": ROOMS})
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_locate_irk_watch")
    assert entity_id is not None
    await service.async_configure({"devices": []})
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_locate_irk_watch") is None
    assert hass.states.get(entity_id) is None


async def test_a_device_without_learning_uses_the_others(hass: HomeAssistant) -> None:
    await _setup(hass)
    service: LocateService = hass.data[DATA_LOCATE]
    second = {**WATCH, "id": "irk_second", "name": "Second", "key": "ffeeddccbbaa99887766554433221100"}
    await service.async_configure({"devices": [WATCH, second], "rooms": ROOMS})
    service.fingerprints["irk_watch"] = Fingerprints({"kitchen": [{"s1": -60.0}], "hall": [{"s1": -80.0}]})
    pooled = service.pooled()
    assert pooled.rooms() == ["kitchen", "hall"]
    # an offline scanner keeps its row and room
    await service.async_configure({"scanner_rooms": {"AA:BB:CC:DD:EE:09": "hall"}})
    rows = service.config()["scanners"]
    assert any(r["source"] == "AA:BB:CC:DD:EE:09" and r.get("offline") for r in rows)
