# Dieser Fork: eigene Möbel

> **In short:** this fork of [Mastershort/neonplan3d](https://github.com/Mastershort/neonplan3d)
> lets an installation import furniture packs it signed itself. Upstream accepts
> packs from three publisher keys only. Everything else is unchanged, and packs
> signed with an own key cannot unlock paid Pro features. See
> [own-furniture/README.md](own-furniture/README.md) to build your own furniture.

NeonPlan 3D nimmt nur Möbel-Packs an, die mit einem der drei Herausgeber-Schlüssel
von Mastershort unterschrieben sind. Eigene Möbel lassen sich damit bauen, aber
nicht importieren: der geheime Schlüssel liegt beim Hersteller. Ein Möbel-Studio
steht auf der Roadmap, wird aber noch nicht angeboten.

Dieser Fork ergänzt genau eine Sache: **eine Installation darf eigene
Herausgeber-Schlüssel führen.** Damit kann jeder seine eigenen Möbel bauen,
unterschreiben und importieren.

## Was bewusst nicht geändert ist

Ein eigener Schlüssel darf **nur eigene Möbel** unterschreiben:

* Pack-IDs müssen mit `local.` oder `studio.` beginnen, damit ein eigenes Pack
  kein gekauftes verdrängt;
* `features` muss leer sein, also **keine Pro-Erweiterungen**.

Das ist dieselbe Beschränkung, die der Hersteller seinem eigenen Studio-Schlüssel
gibt (`STUDIO_KEYS`). Der Fork öffnet den Weg für eigene Möbel, nicht für
bezahlte Funktionen. Wer Pro-Funktionen oder die fertigen Möbel-Packs will,
kauft sie im Shop, und das soll so bleiben: das Projekt lebt davon.

Der Signaturweg selbst bleibt unangetastet. Ohne Schlüsseldatei verhält sich
diese Version wie das Original.

## Die Änderung im Code

Alles in einer Datei, mit `FORK` markiert:

| Datei | Änderung |
|---|---|
| `custom_components/neonplan3d/packs.py` | Block `--- FORK d14tk ... /FORK ---` nach `STUDIO_KEYS`: `LOCAL_KEYS_FILE`, `LOCAL_ID_PREFIXES`, `_local_key_files()`, `local_keys()`. Dazu drei Zeilen Import (`os`, `pathlib`, `re`). |
| `custom_components/neonplan3d/packs.py` → `verify_pack()` | Zwei Einschübe, beide mit `# FORK d14tk` kommentiert: lokale Schlüssel zu den Herausgeber-Schlüsseln dazunehmen, und die Beschränkung auf eigene Möbel durchsetzen. |
| `tests/test_packs_fork.py` | Neu. Hält die Beschränkung fest: eigene Möbel gehen, Pro-Erweiterungen und fremde Pack-IDs nicht. |
| `own-furniture/` | Neu. Anleitung und Beispiel für eigene Möbel. |
| `custom_components/neonplan3d/manifest.json` | `version` mit Fork-Kennung, `issue_tracker` auf dieses Repo. |
| `hacs.json` | `name` mit Fork-Kennung. |
| `tools/fork_release.py` | Neu. Baut das Release-ZIP, weil die Workflows im Fork nicht laufen. |
| `FORK.md` | Diese Datei. |

Der Rest ist unverändert. Der Import-Dialog im Editor
(**Möbel → Möbel-Pack importieren …**) und `tools/fp3dpack.py` zum Unterschreiben
gehören zum Original und werden nur benutzt.

## Updates des Originals einpflegen

Der Fork hat zwei Remotes: `origin` (dieses Repo) und `upstream` (das Original).
Fehlt `upstream`:

```bash
git remote add upstream https://github.com/Mastershort/neonplan3d.git
```

Dann bei jedem neuen Release des Originals:

```bash
git fetch upstream --tags
git checkout main
git merge upstream/main           # oder: git merge v1.21.0
```

**Konflikte sind nur in `packs.py` zu erwarten**, und nur dann, wenn das Original
dort anfasst, was der Fork anfasst: die Importliste am Dateikopf, den Bereich um
`STUDIO_KEYS` oder `verify_pack()`. Die eigenen Zeilen sind mit `FORK` markiert,
also gilt beim Auflösen:

1. Die Änderung des Originals übernehmen.
2. Die mit `FORK` markierten Zeilen daneben wieder einsetzen. Wenn das Original
   `verify_pack()` umbaut, bleiben zwei Dinge zu tun: die lokalen Schlüssel zu
   den Herausgeber-Schlüsseln dazunehmen und die Beschränkung auf eigene Möbel
   nach `validate_payload()` prüfen.
3. Danach **`pytest tests/test_packs_fork.py`** laufen lassen. Diese Tests sind
   der Beweis, dass der Fork noch tut, was er soll: wenn sie durchlaufen, sind
   eigene Möbel importierbar und Pro-Erweiterungen weiter gesperrt. Dazu
   `pytest tests/test_packs.py`, damit der Signaturweg des Originals heil ist.

Nach dem Merge die Version nachziehen und ein Release bauen, siehe unten.

### Wenn das Original ein Möbel-Studio bekommt

Dann ist dieser Fork überflüssig. Den Block in `packs.py` entfernen, zurück auf
das Original wechseln, die eigenen Packs mit dem Studio-Schlüssel neu
unterschreiben lassen.

## Version und Release

HACS installiert hier aus dem Release-Asset (`hacs.json`, `zip_release`).
Upstream baut das ZIP im Workflow `.github/workflows/release.yml` -
**in einem Fork laufen GitHub Actions aber erst, wenn man sie einmal von Hand
freigibt** (Reiter *Actions* im Repo). Solange das nicht passiert ist, baut
`tools/fork_release.py` das ZIP genauso und hängt es an:

```bash
# manifest.json: "version": "1.20.2.1"   (Original + vierte Stelle für den Fork)
git commit -am "1.20.2.1: ..." && git push
gh release create v1.20.2.1 --repo d14tk/neonplan3d --title "1.20.2.1" --notes "..."
python tools/fork_release.py --tag v1.20.2.1
```

`gh` nimmt im Klon eines Forks sonst das **Original** als Ziel. Darum überall
`--repo d14tk/neonplan3d` angeben oder einmal
`gh repo set-default d14tk/neonplan3d` setzen.

Ohne das ZIP am Release findet HACS nichts zu installieren.

Das Schema ist **Originalversion plus vierte Stelle**. So ist auf den ersten
Blick zu sehen, auf welchem Release des Originals der Fork sitzt.

## Herkunft

Fork von [Mastershort/neonplan3d](https://github.com/Mastershort/neonplan3d),
MIT-Lizenz, Copyright (c) 2026 Mastershort. Die Lizenz liegt unverändert in
[LICENSE](LICENSE). Diese Änderungen stehen unter derselben Lizenz.

Wer NeonPlan 3D nutzt, sollte das Original unterstützen: die Möbel-Packs und der
Supporter-Pass im [Shop](https://mastershort.de/neonplan3d/) finanzieren die
Entwicklung. Dieser Fork ersetzt sie nicht, er macht nur eigene Möbel möglich.
