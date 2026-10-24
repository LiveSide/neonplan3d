import assert from "node:assert/strict";
import { test } from "node:test";
import type { Building, Room } from "./model.ts";
import { emptyBuilding, newFloor } from "./model.ts";
import { floorCounts, floorInfoText, initials, locatedPersons, personColor, personsInRooms, roomForState } from "./presence.ts";
import type { HassEntity, HomeAssistant } from "./types.ts";

const st = (entity_id: string, state: string, attributes: Record<string, unknown> = {}): HassEntity => ({ entity_id, state, attributes });

function rect(id: string, name: string, area: string | null, x0: number): Room {
  return { id, name, area_id: area, points: [[x0, 0], [x0 + 4, 0], [x0 + 4, 3], [x0, 3]], floor_material: "wood" };
}

function setup(): { hass: HomeAssistant; building: Building } {
  const building = emptyBuilding();
  building.floors = [{ ...newFloor("eg", "EG", 0), rooms: [rect("r1", "Wohnen", "living_room", 0), rect("r2", "Küche", "kitchen", 4)] }];
  building.presence = [
    { person: "person.mia", sensor: "sensor.mia_area" },
    { person: "person.tom", sensor: "sensor.tom_room" },
    { person: "person.lea", sensor: "sensor.lea_area" },
  ];
  const hass: HomeAssistant = {
    language: "de",
    connection: {} as HomeAssistant["connection"],
    callWS: async () => undefined as never,
    callService: async () => undefined,
    areas: { living_room: { area_id: "living_room", name: "Wohnzimmer" }, kitchen: { area_id: "kitchen", name: "Kitchen" } },
    entities: { "light.a": { entity_id: "light.a", area_id: "kitchen" } },
    states: Object.fromEntries(
      [
        st("person.mia", "home", { friendly_name: "Mia Muster" }),
        st("sensor.mia_area", "Wohnzimmer"),
        st("person.tom", "home", { friendly_name: "Tom" }),
        st("sensor.tom_room", "kitchen"),
        st("person.lea", "not_home", { friendly_name: "Lea" }),
        st("sensor.lea_area", "Wohnzimmer"),
        st("light.a", "on"),
      ].map((s) => [s.entity_id, s]),
    ),
  };
  return { hass, building };
}

test("room sensor states match room names, area names and area ids", () => {
  const { hass, building } = setup();
  assert.equal(roomForState(hass, building, "Wohnzimmer")?.room.id, "r1");
  assert.equal(roomForState(hass, building, "living_room")?.room.id, "r1");
  assert.equal(roomForState(hass, building, "küche")?.room.id, "r2");
  assert.equal(roomForState(hass, building, "not_home"), null);
});

test("people at home are placed in their room; away people are not", () => {
  const { hass, building } = setup();
  const people = personsInRooms(hass, building);
  assert.deepEqual(
    people.map((p) => [p.id, p.roomId, p.initials]),
    [
      ["person.mia", "r1", "MM"],
      ["person.tom", "r2", "TO"],
    ],
  );
  assert.equal(initials("anna"), "AN");
});

test("floor labels count rooms, lights on, open windows and people", () => {
  const { hass, building } = setup();
  const counts = floorCounts(hass, building, new Map(), personsInRooms(hass, building)).get("eg")!;
  assert.deepEqual(counts, { rooms: 2, lightsOn: 1, open: 0, persons: 2 });
  assert.equal(floorInfoText(hass, counts), "2 Räume · 1 Licht an · 2 Pers.");
});

test("located people: a worn device places the person, a phone left elsewhere stands as a thing, away left out", () => {
  const { hass, building } = setup();
  const now = Date.parse("2026-10-23T12:00:00Z");
  const iso = (agoS: number) => new Date(now - agoS * 1000).toISOString();
  const loc = (room: string, person: string | null, name: string, worn: boolean, agoS: number, sinceS = 60, probability = 0.8): HassEntity =>
    st(`sensor.${name.toLowerCase().replace(/\s+/g, "_")}_raum`, "x", { neonplan_locate: true, room_id: room, person, device_name: name, wearable: worn, last_seen: iso(agoS), since: iso(sinceS), probability });
  for (const s of [
    loc("r2", "person.mia", "Mia iPhone", false, 5, 1200, 0.99), // fresher and sure, but lying in the kitchen for 20 minutes
    loc("r1", "person.mia", "Mia Watch", true, 20), // worn, walked into the living room a minute ago: Mia is there
    loc("r2", "person.lea", "Leas Uhr", true, 3), // Lea is away
    loc("r2", null, "Schlüssel", false, 60),
    loc("nowhere", null, "Tag", false, 1),
  ]) {
    hass.states[s.entity_id] = s;
  }
  const people = locatedPersons(hass, building, new Set(), now);
  assert.deepEqual(
    people.map((p) => [p.id, p.roomId, p.thing ?? false, p.tag]),
    [
      ["sensor.schlüssel_raum", "r2", true, "Schlüssel"],
      ["person.mia", "r1", false, "Mia"],
      ["sensor.mia_iphone_raum", "r2", true, "Mia iPhone"],
    ],
  );
  assert.equal(people[1].entity, "sensor.mia_watch_raum");
  assert.equal(people[1].color, personColor("person.mia"));
  // the watch silent for minutes: the freshest device places her
  hass.states["sensor.mia_watch_raum"].attributes.last_seen = iso(600);
  assert.equal(locatedPersons(hass, building, new Set(), now).find((p) => p.id === "person.mia")?.roomId, "r2");
  // the ones already shown by the room sensors are skipped
  assert.equal(locatedPersons(hass, building, new Set(["person.mia"]), now).filter((p) => !p.thing).length, 0);
});

test("located people: watch and phone heard together disagree about the room – the clearly surer one wins, no extra thing", () => {
  const { hass, building } = setup();
  const now = Date.parse("2026-10-23T12:00:00Z");
  const iso = (agoS: number) => new Date(now - agoS * 1000).toISOString();
  const put = (name: string, room: string, worn: boolean, probability: number) =>
    (hass.states[`sensor.${name}_raum`] = st(`sensor.${name}_raum`, "x", { neonplan_locate: true, room_id: room, person: "person.tom", device_name: name, wearable: worn, last_seen: iso(5), since: iso(600), probability }));
  // sitting in the kitchen, the living-room plug behind the seat fools the watch
  put("watch", "r1", true, 0.6);
  put("iphone", "r2", false, 0.85);
  let people = locatedPersons(hass, building, new Set(), now);
  assert.deepEqual(people.map((p) => [p.id, p.roomId, p.thing ?? false]), [["person.tom", "r2", false]]);
  // the phone only a little surer: the watch keeps it, still no phone symbol
  put("iphone", "r2", false, 0.7);
  people = locatedPersons(hass, building, new Set(), now);
  assert.deepEqual(people.map((p) => [p.id, p.roomId, p.thing ?? false]), [["person.tom", "r1", false]]);
});

test("located people: a watch lying still while the phone walks on was taken off – the phone places her, the watch stands as a thing", () => {
  const { hass, building } = setup();
  const now = Date.parse("2026-10-23T12:00:00Z");
  const iso = (agoS: number) => new Date(now - agoS * 1000).toISOString();
  const put = (name: string, room: string, worn: boolean, probability: number, sinceS: number) =>
    (hass.states[`sensor.${name}_raum`] = st(`sensor.${name}_raum`, "x", { neonplan_locate: true, room_id: room, person: "person.mia", device_name: name, wearable: worn, last_seen: iso(5), since: iso(sinceS), probability }));
  // the watch has lain in the living room for an hour, the phone came into the kitchen a minute ago
  put("watch", "r1", true, 0.95, 3600);
  put("iphone", "r2", false, 0.6, 60);
  const people = locatedPersons(hass, building, new Set(), now);
  assert.deepEqual(
    people.map((p) => [p.id, p.roomId, p.thing ?? false]).sort(),
    [["person.mia", "r2", false], ["sensor.watch_raum", "r1", true]],
  );
});
