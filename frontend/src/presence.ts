// Presence and floor summaries: which room a person is in (from a room sensor such as ESPresense or
// Bermuda, whose state names a room or area), and the counts shown on the floor labels.

import { areaEntities, kindOf, openingState, primaryEntities, type OpeningEntities } from "./devices.ts";
import { translate } from "./i18n.ts";
import type { Building, Room } from "./model.ts";
import { centroid } from "./model.ts";
import type { HomeAssistant } from "./types.ts";

export interface PersonMarker {
  id: string;
  name: string;
  initials: string;
  picture: string | null;
  floorId: string;
  roomId: string;
  x: number;
  z: number;
  /** Located people: their own colour, the sensor a tap opens, and the short name under the pin. */
  color?: string;
  entity?: string;
  tag?: string;
  thing?: boolean;
}

export type PersonLook = "figure" | "pin" | "off";

/** How the house shows located people (editor ⚙ Settings → House): a neon figure (default), a pin, or not at all. */
export function personLook(building: Building | null | undefined): PersonLook {
  return building?.settings.person_look ?? "figure";
}

export function personsShown(building: Building | null | undefined): boolean {
  return personLook(building) !== "off";
}

/** Colours of located people: stable per person (by id), bright on the dark neon and the light looks. */
const PERSON_COLORS = ["#ff5fd2", "#37e0ff", "#ffb84d", "#7dff8a", "#b18cff", "#ff7a6b", "#4dd2c0", "#f5e663"];

export function personColor(id: string): string {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PERSON_COLORS[h % PERSON_COLORS.length];
}

const norm = (s: string) => s.toLowerCase().replace(/[_\-]+/g, " ").replace(/\s+/g, " ").trim();

/** Room whose name, area name or area id matches a room sensor's state. */
export function roomForState(hass: HomeAssistant, building: Building, state: string): { floorId: string; room: Room } | null {
  const want = norm(state);
  if (!want || want === "unknown" || want === "unavailable" || want === "not home" || want === "away") return null;
  for (const floor of building.floors) {
    for (const room of floor.rooms) {
      const names = [room.name, room.area_id ?? "", room.area_id ? (hass.areas?.[room.area_id]?.name ?? "") : ""].filter(Boolean).map(norm);
      if (names.includes(want)) return { floorId: floor.id, room };
    }
  }
  return null;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts.length > 1 ? parts[0][0] + parts[parts.length - 1][0] : parts[0].slice(0, 2)).toUpperCase();
}

/** People at home whose room sensor names a room of the plan, spread around the room centre. */
export function personsInRooms(hass: HomeAssistant, building: Building): PersonMarker[] {
  const out: PersonMarker[] = [];
  const perRoom = new Map<string, number>();
  for (const link of building.presence) {
    const person = hass.states[link.person];
    if (!person || !link.sensor) continue;
    // a person who is away is not in any room, whatever the room sensor still says
    if (person.state !== "home" && person.state !== "on") continue;
    const sensor = hass.states[link.sensor];
    if (!sensor) continue;
    const hit = roomForState(hass, building, sensor.state);
    if (!hit) continue;
    const i = perRoom.get(hit.room.id) ?? 0;
    perRoom.set(hit.room.id, i + 1);
    const [cx, cz] = centroid(hit.room.points);
    // next to the room label, one after another on a small circle
    const a = -Math.PI / 2 + 0.9 + i * 1.15;
    const r = 0.75;
    const name = (person.attributes.friendly_name as string | undefined) ?? link.person;
    out.push({
      id: link.person,
      name,
      initials: initials(name),
      picture: (person.attributes.entity_picture as string | undefined) ?? null,
      floorId: hit.floorId,
      roomId: hit.room.id,
      x: cx + Math.cos(a) * r,
      z: cz + Math.sin(a) * r,
    });
  }
  return out;
}

/**
 * People and things NeonPlan's own locating puts in a room: its sensors (attribute neonplan_locate) name a room of
 * the plan. A device of a person who is away is left out; several in one room stand on a small circle.
 */
export function locatedPersons(hass: HomeAssistant, building: Building, skip: ReadonlySet<string> = new Set(), now = Date.now()): PersonMarker[] {
  interface Found {
    entityId: string;
    name: string;
    person: string | null;
    floorId: string;
    room: Room;
    seen: number;
    worn: boolean;
  }
  const found: Found[] = [];
  for (const [entityId, st] of Object.entries(hass.states)) {
    const a = st.attributes;
    if (!entityId.startsWith("sensor.") || a.neonplan_locate !== true || typeof a.room_id !== "string") continue;
    let hit: { floorId: string; room: Room } | null = null;
    for (const floor of building.floors) {
      const room = floor.rooms.find((r) => r.id === a.room_id);
      if (room) hit = { floorId: floor.id, room };
    }
    if (!hit) continue;
    const seen = typeof a.last_seen === "string" ? Date.parse(a.last_seen) : NaN;
    found.push({
      entityId,
      name: typeof a.device_name === "string" ? a.device_name : entityId,
      person: typeof a.person === "string" ? a.person : null,
      floorId: hit.floorId,
      room: hit.room,
      seen: Number.isFinite(seen) ? seen : 0,
      worn: a.wearable === true,
    });
  }
  const out: PersonMarker[] = [];
  const perRoom = new Map<string, number>();
  const place = (f: Found, marker: Omit<PersonMarker, "floorId" | "roomId" | "x" | "z">) => {
    const i = perRoom.get(f.room.id) ?? 0;
    perRoom.set(f.room.id, i + 1);
    const [cx, cz] = centroid(f.room.points);
    const angle = -Math.PI / 2 + 0.9 + i * 1.15;
    out.push({ ...marker, floorId: f.floorId, roomId: f.room.id, x: cx + Math.cos(angle) * 0.75, z: cz + Math.sin(angle) * 0.75 });
  };
  const thing = (f: Found, color: string) =>
    place(f, { id: f.entityId, name: f.name, initials: f.name.slice(0, 1).toUpperCase(), picture: null, color, entity: f.entityId, tag: f.name, thing: true });
  const byPerson = new Map<string, Found[]>();
  for (const f of found) {
    if (!f.person) thing(f, personColor(f.entityId));
    else byPerson.set(f.person, [...(byPerson.get(f.person) ?? []), f]);
  }
  for (const [personId, list] of byPerson) {
    if (skip.has(personId)) continue;
    const person = hass.states[personId];
    // away: neither the person nor a device left at home is shown as the person
    if (person && person.state !== "home" && person.state !== "on") continue;
    // a worn device (watch) heard in the last two minutes tells where the person is; else the freshest device
    const fresh = list.filter((f) => f.worn && now - f.seen < 120_000);
    const main = (fresh.length ? fresh : list).reduce((a, b) => (b.seen > a.seen ? b : a));
    const name = (person?.attributes.friendly_name as string | undefined) ?? main.name;
    place(main, {
      id: personId,
      name,
      initials: initials(name),
      picture: (person?.attributes.entity_picture as string | undefined) ?? null,
      color: personColor(personId),
      entity: main.entityId,
      tag: name.split(/\s+/)[0],
    });
    // a phone left in another room stands there as a thing ("where is my iPhone")
    for (const f of list) if (f !== main && f.room.id !== main.room.id) thing(f, personColor(personId));
  }
  return out;
}

export interface FloorCounts {
  rooms: number;
  lightsOn: number;
  open: number;
  persons: number;
}

/** Counts per floor for the floor labels in the house view. */
export function floorCounts(hass: HomeAssistant, building: Building, links: Map<string, OpeningEntities>, persons: PersonMarker[]): Map<string, FloorCounts> {
  const out = new Map<string, FloorCounts>();
  const on = (id: string | null) => !!id && hass.states[id]?.state === "on";
  for (const floor of building.floors) {
    const lights = new Set<string>();
    // main entities only: a LED strip with 30 segment entities is one light
    for (const room of floor.rooms) for (const id of primaryEntities(hass, areaEntities(hass, room.area_id))) if (kindOf(id) === "light") lights.add(id);
    for (const pl of floor.placements) if (kindOf(pl.entity_id) === "light") lights.add(pl.entity_id);
    const open = floor.openings.filter((o) => {
      const l = links.get(o.id);
      if (!l) return false;
      // a garage door counts as open while its cover is not (almost) down
      if (o.type === "garage") return (openingState(hass, l, "garage").cover ?? 1) < 0.95;
      if (o.type === "door") return on(l.contact) || on(l.contact2 ?? null);
      const s = openingState(hass, l, "window");
      return s.open > 0.5 || s.tilt > 0.5 || s.open2 > 0.5 || s.tilt2 > 0.5;
    }).length;
    out.set(floor.id, {
      rooms: floor.rooms.length,
      lightsOn: [...lights].filter((id) => hass.states[id]?.state === "on").length,
      open,
      persons: persons.filter((p) => p.floorId === floor.id).length,
    });
  }
  return out;
}

export function floorInfoText(hass: HomeAssistant | undefined, c: FloorCounts): string {
  const parts = [c.rooms === 1 ? translate(hass, "floor_rooms_one") : translate(hass, "floor_rooms", { n: c.rooms })];
  if (c.lightsOn) parts.push(translate(hass, "floor_lights", { n: c.lightsOn }));
  if (c.open) parts.push(translate(hass, "floor_open", { n: c.open }));
  if (c.persons) parts.push(translate(hass, "floor_persons", { n: c.persons }));
  return parts.join(" · ");
}
