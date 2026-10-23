"""Spoken answers of the locating feature, straight from Home Assistant (no screen needed):
"Wo ist Torsten?", "Wo ist mein iPhone?", "Wer ist zu Hause?", "Lass mein iPhone klingeln"."""

from __future__ import annotations

import re
import time
from typing import Any

from homeassistant.core import HomeAssistant

from .service import LocateService

_ART_DE = r"(?:mein|meine|meinen|der|die|das|den)?"
_WHERE = {
    "de": re.compile(r"^(?:wo (?:ist|steckt|liegt|sind)|finde|such[e]?)\s+" + _ART_DE + r"\s*(?P<what>.+?)[?.!]*$"),
    "en": re.compile(r"^(?:where(?:'s| is| are)|find)\s+(?:my|the)?\s*(?P<what>.+?)[?.!]*$"),
}
_WHO = {
    "de": re.compile(r"^wer ist (?:gerade |denn )?(?:zu ?hause|daheim|da|im haus)[?.!]*$"),
    "en": re.compile(r"^who(?:'s| is) (?:at )?home[?.!]*$"),
}
_RING = {
    "de": re.compile(r"^(?:lass|lasse)\s+" + _ART_DE + r"\s*(?P<what>.+?)\s+(?:klingeln|piepen|läuten)[?.!]*$"),
    "en": re.compile(r"^(?:ring|beep)\s+(?:my|the)?\s*(?P<what>.+?)[?.!]*$"),
}
_TEXT = {
    "de": {
        "in": "{who} ist im Raum {room}.",
        "in_ago": "{who} war zuletzt im Raum {room}, vor {min} Minuten.",
        "away": "{who} ist gerade nicht zu Hause.",
        "unheard": "Ich höre {who} gerade nicht.",
        "nobody": "Gerade ist niemand zu Hause, den ich orten kann.",
        "home": "Zu Hause: {list}.",
        "ring": "{who} klingelt jetzt.",
        "no_ring": "Für {who} ist keine App zum Klingeln eingestellt.",
    },
    "en": {
        "in": "{who} is in the {room}.",
        "in_ago": "{who} was last in the {room}, {min} minutes ago.",
        "away": "{who} is not at home right now.",
        "unheard": "I can't hear {who} right now.",
        "nobody": "Nobody I can locate is at home right now.",
        "home": "At home: {list}.",
        "ring": "{who} is ringing now.",
        "no_ring": "No app to ring is set for {who}.",
    },
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("\u2019", "'")).strip()


def _person_name(hass: HomeAssistant, entity_id: str | None) -> str | None:
    state = hass.states.get(entity_id) if entity_id else None
    return str(state.attributes.get("friendly_name") or entity_id) if state else None


def _match(hass: HomeAssistant, service: LocateService, what: str) -> tuple[str, list[dict[str, Any]]] | None:
    """The devices a name means: a device by its name, or every device of a person (watch first)."""
    want = _norm(what)
    for device in service.devices:
        if _norm(device["name"]) == want or want in _norm(device["name"]).split(" "):
            return device["name"], [device]
    for device in service.devices:
        if want and want in _norm(device["name"]):
            return device["name"], [device]
    by_person: dict[str, list[dict[str, Any]]] = {}
    for device in service.devices:
        if device.get("person"):
            by_person.setdefault(device["person"], []).append(device)
    for person, devices in by_person.items():
        name = _person_name(hass, person) or ""
        if want and (want == _norm(name) or want in _norm(name).split(" ")):
            return name, devices
    return None


def _where(hass: HomeAssistant, service: LocateService, who: str, devices: list[dict[str, Any]], lang: str) -> str:
    t = _TEXT[lang]
    person = devices[0].get("person")
    if person and (state := hass.states.get(person)) and state.state not in ("home", "on"):
        return t["away"].format(who=who)
    # a worn device heard in the last two minutes tells where the person is; else the freshest one
    now = time.time()
    placed = [(d, service.state.get(d["id"]) or {}) for d in devices]
    placed = [(d, st) for d, st in placed if st.get("room_name")]
    worn = [st for d, st in placed if d.get("wearable") and now - (st.get("last_seen") or 0) < 120]
    pool = worn or [st for _d, st in placed]
    best = max(pool, key=lambda st: st.get("last_seen") or 0, default=None)
    if best is None:
        return t["unheard"].format(who=who)
    ago = int((time.time() - (best.get("last_seen") or time.time())) // 60)
    if ago >= 3:
        return t["in_ago"].format(who=who, room=best["room_name"], min=ago)
    return t["in"].format(who=who, room=best["room_name"])


async def async_answer(hass: HomeAssistant, service: LocateService | None, text: str, language: str) -> str | None:
    """The answer to a locating question, or None when the sentence is no such question."""
    if service is None or not service.devices:
        return None
    lang = language if language in _TEXT else "en"
    sentence = _norm(text)
    t = _TEXT[lang]
    if _WHO[lang].match(sentence):
        names: list[str] = []
        for device in service.devices:
            st = service.state.get(device["id"]) or {}
            if not st.get("room_name"):
                continue
            who = _person_name(hass, device.get("person")) or device["name"]
            if who not in [n.split(" (")[0] for n in names]:
                names.append(f"{who} ({st['room_name']})")
        return t["home"].format(list=", ".join(names)) if names else t["nobody"]
    if m := _RING[lang].match(sentence):
        found = _match(hass, service, m["what"])
        if found is None:
            return None
        who, devices = found
        notify = next((d.get("notify") for d in devices if d.get("notify")), None)
        if not notify:
            return t["no_ring"].format(who=who)
        await ring(hass, notify, lang)
        return t["ring"].format(who=who)
    if m := _WHERE[lang].match(sentence):
        found = _match(hass, service, m["what"])
        if found is None:
            return None
        who, devices = found
        return _where(hass, service, who, devices, lang)
    return None


async def ring(hass: HomeAssistant, notify: str, lang: str) -> None:
    """A loud notification through the Home Assistant app (critical on iPhone, alarm channel on Android)."""
    service = notify.removeprefix("notify.")
    message = "NeonPlan sucht dich 🔔" if lang == "de" else "NeonPlan is looking for you 🔔"
    await hass.services.async_call(
        "notify",
        service,
        {
            "title": "NeonPlan",
            "message": message,
            "data": {
                "push": {"sound": {"name": "default", "critical": 1, "volume": 1.0}},
                "ttl": 0,
                "priority": "high",
                "channel": "alarm_stream",
            },
        },
        blocking=False,
    )
