"""Fork feature: putting packs into the store of a machine over SSH (see FORK.md).

tools/packs_store.py is the way to install many packs at once, in place of picking each file in
the panel. It writes .storage/neonplan3d.packs directly, so what it refuses never reaches Home
Assistant and what it lets through must look exactly like an imported pack. These tests pin that
part; everything that talks over SSH is left out, it has nothing to decide.
"""

from __future__ import annotations

import base64
import copy
import importlib.util
import json
from pathlib import Path
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

from custom_components.neonplan3d import packs

TOOLS = Path(__file__).resolve().parent.parent / "tools"

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


def _tool(name: str):
    """Load a tool module by path (tools/ is not a package)."""
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    spec = importlib.util.spec_from_file_location(f"fp3d_{name}", TOOLS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def written(private: Ed25519PrivateKey, kid: str, payload: dict, into: Path) -> Path:
    """A signed pack file on disk, as the tool gets it."""
    signature = base64.b64encode(private.sign(packs.canonical(payload))).decode()
    into.write_text(json.dumps({"payload": payload, "signature": {"key": kid, "sig": signature}}), encoding="utf-8")
    return into


def test_entry_looks_like_an_imported_pack(own_key, tmp_path) -> None:
    """The entry carries the payload plus what an import adds: source, signature and the time."""
    tool = _tool("packs_store")
    private, kid = own_key
    file = written(private, kid, copy.deepcopy(PAYLOAD), tmp_path / "local.test.fp3dpack")
    entry = tool.entry_of(file, None)
    assert entry["id"] == "local.test"
    assert entry["signature"]["key"] == kid
    assert entry["source"]["items"][0]["id"] == "crate"
    assert entry["imported_at"] > 0
    # the defaults the schema fills in are in the entry, not in the signed source
    assert entry["items"][0]["mount"] == "floor"
    assert "mount" not in entry["source"]["items"][0]


def test_a_changed_pack_never_reaches_the_store(own_key, tmp_path) -> None:
    """Editing the file after signing breaks the signature, and the tool refuses it."""
    tool = _tool("packs_store")
    private, kid = own_key
    payload = copy.deepcopy(PAYLOAD)
    file = written(private, kid, payload, tmp_path / "local.test.fp3dpack")
    broken = json.loads(file.read_text(encoding="utf-8"))
    broken["payload"]["name"] = "Something else"
    file.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(packs.PackError) as refused:
        tool.entry_of(file, None)
    assert refused.value.code == "bad_signature"


def test_a_pack_source_is_not_a_pack_file(tmp_path) -> None:
    """The source from own-furniture/README.md has to be signed first; raw, it is no pack file."""
    tool = _tool("packs_store")
    file = tmp_path / "source.json"
    file.write_text(json.dumps(PAYLOAD), encoding="utf-8")
    with pytest.raises(packs.PackError) as refused:
        tool.entry_of(file, None)
    assert refused.value.code == "not_a_pack"


def test_a_file_without_a_signature_is_refused(tmp_path) -> None:
    """Wrapped like a pack but with the signature block missing."""
    tool = _tool("packs_store")
    file = tmp_path / "half.fp3dpack"
    file.write_text(json.dumps({"payload": PAYLOAD}), encoding="utf-8")
    with pytest.raises(packs.PackError) as refused:
        tool.entry_of(file, None)
    assert refused.value.code == "unsigned"


def test_a_pack_bound_elsewhere_is_refused(own_key, tmp_path) -> None:
    """A pack bound to one installation only goes into that one, by its fingerprint.

    The binding is checked against the fingerprint the tool reads from core.uuid; without one
    (instance=None) packs.py does not check it at all, which is why the tool says so.
    """
    tool = _tool("packs_store")
    private, kid = own_key
    payload = copy.deepcopy(PAYLOAD) | {"instance": packs.fingerprint("another-installation")}
    file = written(private, kid, payload, tmp_path / "bound.fp3dpack")
    with pytest.raises(packs.PackError) as refused:
        tool.entry_of(file, packs.fingerprint("this-installation"))
    assert refused.value.code == "wrong_instance"
    assert tool.entry_of(file, packs.fingerprint("another-installation"))["id"] == "local.test"
    assert tool.entry_of(file, None)["id"] == "local.test"


def test_installing_again_replaces_instead_of_doubling() -> None:
    """A newer release of the same pack takes the place of the installed one."""
    tool = _tool("packs_store")
    store = {"data": {"packs": [{"id": "local.test", "release": 1, "items": []}, {"id": "local.other", "items": []}]}}
    tool.merge(store, [{"id": "local.test", "release": 2, "items": []}])
    rows = store["data"]["packs"]
    assert [p["id"] for p in rows] == ["local.test", "local.other"]
    assert next(p for p in rows if p["id"] == "local.test")["release"] == 2


def test_remove_takes_only_what_was_named() -> None:
    tool = _tool("packs_store")
    store = {"data": {"packs": [{"id": "local.a"}, {"id": "local.b"}, {"id": "mastershort.living"}]}}
    assert tool.drop(store, ["local.a", "local.missing"]) == 1
    assert [p["id"] for p in store["data"]["packs"]] == ["local.b", "mastershort.living"]


def test_the_store_as_it_was_is_saved_readable(tmp_path) -> None:
    """The copy is written before anything else and can be read back as it stood."""
    tool = _tool("packs_store")
    store = {"version": 1, "key": "neonplan3d.packs", "data": {"packs": [{"id": "local.a", "items": []}]}}
    path = tool.save_copy(store, tmp_path / "backups")
    assert json.loads(path.read_text(encoding="utf-8")) == store
