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
