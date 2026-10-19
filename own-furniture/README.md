# Eigene Möbel bauen und importieren

Nur in diesem Fork, siehe [../FORK.md](../FORK.md). Gebraucht wird Python mit
`cryptography` und `voluptuous`.

Eigene Möbel sind aus Quadern, Zylindern und Lofts gebaut, so wie die
eingebauten. Das Format steht vollständig in [../docs/packs.md](../docs/packs.md),
eine Vorlage mit allen vier Formen liegt in [example.json](example.json).

## 1. Schlüssel erzeugen, einmalig

```bash
python tools/fp3dpack.py keygen private/moebel-signing-key.pem
```

Das schreibt den geheimen Schlüssel (von `.gitignore` erfasst, er darf nie ins
Repo) und gibt den öffentlichen aus:

```
    "c37e797cc962": "BJQZ…=",
```

**Backup machen.** Ohne diesen Schlüssel lassen sich keine Updates der eigenen
Packs mehr unterschreiben, und ein neuer Schlüssel braucht wieder Schritt 2.

## 2. Schlüssel am Home Assistant eintragen

Eine Datei `neonplan3d_publishers.json` **neben der `configuration.yaml`**, also
`/config/neonplan3d_publishers.json`:

```json
{
  "c37e797cc962": "BJQZ…="
}
```

Mehrere Schlüssel sind erlaubt, einer pro Zeile. Die Datei liegt außerhalb der
Integration und übersteht darum HACS-Updates. Ein Neustart ist nicht nötig, sie
wird bei jedem Import gelesen.

Zum Prüfen vor dem Import: `NEONPLAN3D_PUBLISHERS` auf eine solche Datei zeigen
lassen, dann arbeitet `fp3dpack.py verify` genau wie Home Assistant.

## 3. Möbel beschreiben

Dafür gibt es drei Wege. Der erste braucht kein 3D-Programm, der zweite nimmt
ein fertiges Modell, der dritte eine ganze Möbelbibliothek.

### 3a. Von Hand

[example.json](example.json) kopieren und anpassen. Wichtig:

* `id` des Packs muss mit **`local.`** oder `studio.` beginnen.
* `features` darf nicht gesetzt sein; eigene Schlüssel schalten keine
  Pro-Erweiterungen frei (so gewollt, siehe [../FORK.md](../FORK.md)).
* `size` ist die Standardgröße in Metern. Alles in `parts` sind **Anteile**
  davon: `x`/`z` die Mitte (−0,5 bis 0,5, vorne ist `+z`), `w`/`d` Breite und
  Tiefe, `y` die Unterkante und `h` die Höhe (jeweils 0 bis 1).
* Farben entweder `#rrggbb` oder eine Rolle der Palette (`body`, `fabric`,
  `cushion`, `wood`, `white`, `metal`, `dark`, `glass`, `plant`, `pot`,
  `accent`) — Rollen passen sich dem Look an.
* Höchstens 60 Teile pro Möbel, höchstens 200 Möbel pro Pack.

### 3b. Aus einem 3D-Modell

`tools/mesh2pack.py` formt aus einem Modell (OBJ, GLB, STL, PLY, DAE, 3DS) die
Quader und Zylinder, aus denen ein Möbel hier besteht. Ein Mesh lässt sich nicht
importieren — das Format kennt keine Dreiecke —, also wird das Modell zerlegt:
erst nach seinen Materialien und den Teilen, die zusammenhängen, dann wird jedes
davon mit den größten Kästen ausgelegt, die hineinpassen.

```bash
python tools/mesh2pack.py item stuhl.glb --id stuhl \
    --name "de=Stuhl,en=Chair" --size 0.45 0.5 0.9 -o stuhl.json
python tools/mesh2pack.py preview stuhl.json -o stuhl.png     # erst ansehen
python tools/mesh2pack.py pack stuhl.json tisch.json \
    --id local.esszimmer --name "Esszimmer" -o esszimmer.json
```

`--size` ist die echte Größe in Metern (Breite, Tiefe, Höhe); ohne sie wird die
Größe des Modells genommen. Die Vorderseite gehört nach **+z**, die Höhe nach
y. Weitere Schalter:

| Schalter | Wofür |
|---|---|
| `--parts 46` | wie viele Teile höchstens (bis 60; mehr Teile, mehr Ähnlichkeit) |
| `--grid 24` | wie fein das Modell abgetastet wird |
| `--tol 0.8` | wie voll eine Schicht sein muss, damit ein Kasten weiterwächst |
| `--surface` | die Oberseite trägt anderes (Tisch, Arbeitsplatte) |
| `--mount wall` | hängt an der Wand statt auf dem Boden |
| `--light table` | ist eine Lampe dieser Art |
| `--plant` | Grün darf Pflanzengrün bedeuten (sonst gilt es als Stoff) |

Die Farben kommen aus den Materialnamen und -farben des Modells und werden auf
die Rollen der Palette abgebildet, damit importierte Möbel im Look des Plans
bleiben statt ihre eigenen Farben mitzubringen.

Gute Vorlagen sind Modelle, die aus benannten Bauteilen bestehen
(`seat`, `legs`, `frame`). Ein Modell aus einem einzigen Klumpen ohne
Materialien wird zu einem groben Block.

### 3c. Aus einer Möbelbibliothek

Sweet Home 3D veröffentlicht auf [sweethome3d.com/importModels](https://www.sweethome3d.com/importModels.jsp)
freie Möbelbibliotheken (`.sh3f`). Die bringen mit, was einem Modell aus dem Netz
fast immer fehlt: die echte Größe des Stücks, seine Kategorie und den Namen in
zwanzig Sprachen. `tools/sh3d_import.py` macht daraus fertige Packs.

```bash
python tools/sh3d_import.py BlendSwap-CC-0.sh3f Contributions.sh3f \
    --out packs/ --id local.moebel --name "Möbel" --by-room \
    --credits packs/QUELLEN.md
```

`--by-room` legt ein Pack je Raum an (Wohnen, Küche, Bad, Schlafen, Büro,
Licht, Außen, Treppen, Diverses) statt eines großen. Aus der Kategorie wird
abgeleitet, was NeonPlan 3D zum Platzieren braucht: eine Lampe bekommt ihre
Lichtart, ein Tisch trägt etwas, eine Treppe schneidet ihr Loch, ein Auto
parkt. Türen und Fenster werden ausgelassen, die zeichnet NeonPlan 3D selbst.

Jedes Möbel wird gegen das Schema geprüft und mit dem Modell verglichen; was zu
weit danebenliegt, fällt mit `--min-iou` heraus (Standard 0,45). Am Ende steht,
wie ähnlich die Stücke geworden sind. `--credits` schreibt die Liste der Urheber
und Lizenzen — **die Lizenz der Bibliothek gilt weiter**, CC-0 ist frei, Free Art
verlangt Namensnennung.

## 4. Unterschreiben

```bash
python tools/fp3dpack.py sign own-furniture/example.json \
    --key private/moebel-signing-key.pem \
    --out private/local-example.fp3dpack
```

Prüfen, wie Home Assistant es tut:

```bash
NEONPLAN3D_PUBLISHERS=/pfad/zu/neonplan3d_publishers.json \
    python tools/fp3dpack.py verify private/local-example.fp3dpack
```

## 5. Importieren

Im NeonPlan-Panel: **Bearbeiten → Möbel → Möbel-Pack importieren …** und die
`.fp3dpack`-Datei auswählen. Die Möbel stehen danach im Katalog.

### Viele Packs auf einmal

Für eine ganze Bibliothek ist das Klicken mühsam. `tools/packs_store.py`
schreibt den Pack-Store über SSH:

```bash
python tools/packs_store.py list
python tools/packs_store.py install packs/*.fp3dpack --restart
python tools/packs_store.py remove local.moebel.bad --restart
```

Jedes Pack wird vorher genau so geprüft wie beim Import über das Panel — was
hier durchfällt, käme auch dort nicht an. `--dry-run` zeigt nur, was geschrieben
würde; der bisherige Store wird davor als Datei gesichert (`--backups`).

Home Assistant liest `.storage` nur beim Start: ohne `--restart` wirkt das
Einspielen erst beim nächsten Start. Beim SSH-Addon ist der Benutzer `root`;
mit einem anderen braucht es `--sudo`. Wohin die Verbindung geht, sagen
`--host`, `--port` und `--ssh-key`.

## Updates eines eigenen Packs

Dieselbe `id` behalten und `release` hochzählen (`"release": 2`). Beim Import
ersetzt das neue Pack das installierte. Möbel, die schon im Plan stehen,
behalten ihre Position.

## Wenn der Import scheitert

| Meldung | Ursache |
|---|---|
| `unknown_publisher` | Der Schlüssel steht nicht in `neonplan3d_publishers.json`, oder die Datei liegt am falschen Ort. |
| `bad_signature` mit Hinweis auf eigene Möbel | Pack-`id` beginnt nicht mit `local.`/`studio.`, oder `features` ist gesetzt. |
| `bad_signature` ohne Hinweis | Die Datei wurde nach dem Unterschreiben geändert. Neu unterschreiben. |
| `invalid_content` | Das Pack passt nicht zum Format, die Meldung nennt das Feld. |
| `unsigned` | Die Datei hat keinen `signature`-Block, also wurde `sign` nicht ausgeführt. |
