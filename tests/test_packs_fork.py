"""Fork feature: publisher keys of this installation (see FORK.md).

Upstream only accepts the three keys in PACK_PUBLIC_KEYS. This fork also reads keys from
neonplan3d_publishers.json, restricted to own furniture: pack ids "local.*" or "studio.*"
and no Pro features. These tests pin that restriction, so a merge of a new upstream
release shows at once if it broke.
"""

from __future__ import annotations

import base64
import copy
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

from custom_components.neonplan3d import packs

PAYLOAD = {
    "format": "fp3dpack",
    "version": 1,
    "id": "local.test",
    "name": "Testpack",
    "publisher": "Owner",
    "items": [
        {
            "id": "crate",
            "name": {"de": "Kiste", "en": "Crate"},
            "size": [0.5, 0.4, 0.4],
            "parts": [{"shape": "box", "x": 0, "z": 0, "w": 1, "d": 1, "y": 0, "h": 1, "color": "wood"}],
        }
    ],
}


@pytest.fixture(name="own_key")
def own_key_fixture(tmp_path, monkeypatch):
    """An own signing key, listed in a publisher file the module reads."""
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    kid = packs.key_id(raw)
    file = tmp_path / packs.LOCAL_KEYS_FILE
    file.write_text(json.dumps({kid: base64.b64encode(raw).decode()}), encoding="utf-8")
    monkeypatch.setenv("NEONPLAN3D_PUBLISHERS", str(file))
    return private, kid


def pack(private: Ed25519PrivateKey, kid: str, payload: dict) -> str:
    """A pack file signed with that key.

    The signature covers the payload as written, not the validated one: validation
    fills in defaults, which would change the bytes.
    """
    signature = base64.b64encode(private.sign(packs.canonical(payload))).decode()
    return json.dumps({"payload": payload, "signature": {"key": kid, "sig": signature}})


def test_own_key_is_found(own_key) -> None:
    """The key file is read and its key id matches its public key."""
    _, kid = own_key
    assert list(packs.local_keys()) == [kid]


def test_own_furniture_is_accepted(own_key) -> None:
    """A "local." pack signed with an own key imports."""
    private, kid = own_key
    payload = packs.verify_pack(pack(private, kid, copy.deepcopy(PAYLOAD)))
    assert payload["id"] == "local.test"
    assert payload["items"][0]["id"] == "crate"


def test_studio_prefix_is_accepted(own_key) -> None:
    """The prefix studio. works as well, like the publisher's own studio key."""
    private, kid = own_key
    source = copy.deepcopy(PAYLOAD) | {"id": "studio.mine"}
    assert packs.verify_pack(pack(private, kid, source))["id"] == "studio.mine"


def test_without_key_file_nothing_changes(own_key, monkeypatch) -> None:
    """Without the file the fork behaves like upstream: unknown publisher."""
    private, kid = own_key
    monkeypatch.delenv("NEONPLAN3D_PUBLISHERS")
    monkeypatch.setattr(packs, "_local_key_files", lambda: [])
    with pytest.raises(packs.PackError) as err:
        packs.verify_pack(pack(private, kid, copy.deepcopy(PAYLOAD)))
    assert err.value.code == "unknown_publisher"


def test_own_key_cannot_unlock_pro_features(own_key) -> None:
    """The point of the restriction: no own key unlocks anything that is for sale."""
    private, kid = own_key
    source = copy.deepcopy(PAYLOAD) | {"features": ["energy_pro"]}
    with pytest.raises(packs.PackError) as err:
        packs.verify_pack(pack(private, kid, source))
    assert err.value.code == "bad_signature"


def test_own_key_cannot_sign_module_code(own_key) -> None:
    """Module code is JavaScript the loader runs, not furniture. Upstream holds its own studio key
    to the same line (STUDIO_KEYS), so an own key must not sign it either."""
    private, kid = own_key
    source = copy.deepcopy(PAYLOAD) | {"module": {"api": 1, "kind": "voice", "code": "export default () => {};"}}
    with pytest.raises(packs.PackError) as err:
        packs.verify_pack(pack(private, kid, source))
    assert err.value.code == "bad_signature"


def test_own_key_cannot_replace_a_bought_pack(own_key) -> None:
    """An id outside local./studio. is refused, so a purchased pack stays."""
    private, kid = own_key
    source = copy.deepcopy(PAYLOAD) | {"id": "mastershort.kitchen"}
    with pytest.raises(packs.PackError) as err:
        packs.verify_pack(pack(private, kid, source))
    assert err.value.code == "bad_signature"


def test_changed_after_signing_is_refused(own_key) -> None:
    """The signature still covers the whole payload."""
    private, kid = own_key
    data = json.loads(pack(private, kid, copy.deepcopy(PAYLOAD)))
    data["payload"]["items"][0]["size"] = [9, 9, 9]
    with pytest.raises(packs.PackError) as err:
        packs.verify_pack(json.dumps(data))
    assert err.value.code == "bad_signature"


def test_key_id_must_match_the_public_key(tmp_path, monkeypatch) -> None:
    """A typo in the key id is ignored instead of shadowing a publisher key."""
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    file = tmp_path / packs.LOCAL_KEYS_FILE
    file.write_text(json.dumps({"0123456789ab": base64.b64encode(raw).decode()}), encoding="utf-8")
    monkeypatch.setenv("NEONPLAN3D_PUBLISHERS", str(file))
    assert packs.local_keys() == {}


def test_a_publisher_key_cannot_be_overwritten(tmp_path, monkeypatch) -> None:
    """A key file may not replace one of the three keys compiled in."""
    kid = next(iter(packs.PACK_PUBLIC_KEYS))
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    file = tmp_path / packs.LOCAL_KEYS_FILE
    file.write_text(json.dumps({kid: base64.b64encode(raw).decode()}), encoding="utf-8")
    monkeypatch.setenv("NEONPLAN3D_PUBLISHERS", str(file))
    assert packs.local_keys() == {}
