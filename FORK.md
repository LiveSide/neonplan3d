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

Dazu kommen zwei Werkzeuge, die das Bauen abnehmen. Ein Möbel besteht hier aus
Quadern, Zylindern und Lofts, nicht aus Dreiecken — ein Mesh lässt sich also
nicht einfach importieren. `tools/mesh2pack.py` zerlegt ein 3D-Modell in genau
diese Teile: erst nach Materialien und zusammenhängenden Stücken, dann wird
jedes mit den größten Kästen ausgelegt, die hineinpassen.
`tools/sh3d_import.py` setzt darauf auf und liest eine ganze
Möbelbibliothek — die freien Sammlungen von Sweet Home 3D bringen mit, was
einem Modell aus dem Netz fast immer fehlt: die echte Größe des Stücks, seine
Kategorie und den Namen in zwanzig Sprachen.

Ein drittes Werkzeug nimmt das Einspielen ab. Über das Panel wird jede Datei
einzeln ausgewählt; `tools/packs_store.py` schreibt den Pack-Store eines Home
Assistant über SSH und prüft vorher jedes Pack genau so, wie die Integration es
beim Import tut: Signatur gegen die Schlüssel dieses Repositorys, Inhalt gegen
das echte Schema, und ein an eine Installation gebundenes Pack gegen deren
Fingerabdruck. Home Assistant liest `.storage` nur beim Start, darum wirkt das
Geschriebene erst nach einem Neustart (`--restart` löst ihn aus).

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
| `tools/mesh2pack.py` | Neu. Formt aus einem 3D-Modell (OBJ, GLB, STL, …) die Quader und Zylinder eines Pack-Möbels, misst die Ähnlichkeit und zeichnet eine Vorschau. Braucht `numpy`, `scipy`, `trimesh`, `Pillow`. |
| `tools/sh3d_import.py` | Neu. Liest eine Sweet-Home-3D-Möbelbibliothek (`.sh3f`) und macht daraus fertige Packs, je ein Pack pro Raum. |
| `tests/test_mesh2pack.py` | Neu. Hält fest, was die beiden Werkzeuge liefern müssen: eine hohle Hülle wird massiv, ein offenes Regalfach bleibt offen, jedes erzeugte Möbel besteht `ITEM_SCHEMA`. |
| `custom_components/neonplan3d/manifest.json` | `version` mit Fork-Kennung, `issue_tracker` auf dieses Repo. |
| `hacs.json` | `name` mit Fork-Kennung. |
| `frontend/src/viewer/earth.ts` | `coverAbove()`: nur Flächen auf dem Gelände decken einen Lichtschacht zu. Ein Balkon im Obergeschoss zog den Schachtrand sonst meterhoch zu sich hinauf. Upstream gemeldet als [#602](https://github.com/Mastershort/neonplan3d/issues/602). |
| `frontend/src/viewer/earth.test.ts` | Neuer Test dazu: Balkon oben hebt nicht, Balkon im Erdgeschoss hebt weiter. |
| `custom_components/neonplan3d/frontend/*.js` | Die gebauten Bundles. Seit 1.20.2.3 weichen `neonplan3d.js`, `-3d.js`, `-editor.js`, `-card-editor.js` und `-fun.js` vom Original ab (Änderungen bzw. Fork-Versionsnummer), `-voice.js` und `-timetravel.js` sind bitgleich. Dazu `site/import/neonplan-import.js` (Texte aus `i18n.ts`). |
| `tools/fork_release.py` | Neu. Stempelt die Version in die Bundles und baut das Release-ZIP, weil die Workflows im Fork nicht laufen. |
| `frontend/src/viewer/lighting.ts`, `lighting.test.ts` | Wände blocken Licht mit ihrem Footprint, Säulen werfen Schatten. Siehe [Weitere Änderungen im Frontend](#weitere-änderungen-im-frontend-12023-und-12024). |
| `frontend/src/model.ts`, `model.test.ts`, `viewer/viewer3d.ts`, `components/editor.ts`, `i18n.ts`, `custom_components/neonplan3d/schema.py`, `tests/test_schema.py` | Etagenfeld `attached`: eine Etage gehört zur Etage darüber oder darunter (Straßenniveau mit Garagen unter der Wohnung). Siehe unten. |
| `frontend/src/components/view3d.ts`, `viewer/viewer3d.ts` | Pack-Lampen leuchten aus der Mitte ihrer leuchtenden Teile. Siehe unten. |
| `FORK.md` | Diese Datei. |

Der Rest ist unverändert. Der Import-Dialog im Editor
(**Möbel → Möbel-Pack importieren …**) und `tools/fp3dpack.py` zum Unterschreiben
gehören zum Original und werden nur benutzt.

## Weitere Änderungen im Frontend (1.20.2.3 und 1.20.2.4)

Vier Korrekturen aus dem Betrieb, alle mit Tests. Sie betreffen nur die
Darstellung; am gespeicherten Plan ändert sich nichts außer dem neuen, optionalen
Etagenfeld `attached` und der Einstellung `rain_warning_entity`.

### Wände werfen Schatten mit ihrer ganzen Dicke, Säulen werfen Schatten

**Problem.** Eine Lampe an der Außenseite einer Außenwand leuchtet um die
Hausecke herum: der Rasen vor der Nachbarwand und eine Nische hinter der Ecke
werden hell, obwohl die Wand dazwischen steht. Säulen werfen gar keinen Schatten.

**Ursache.** `shadowed()` in `frontend/src/viewer/lighting.ts` prüft nur, ob die
Linie Lampe → Punkt die Linie `a → b` einer Wand kreuzt. Bei einer Außenwand ist
das die Raumkante, also die *Innenseite*; die Wand wächst von dort nach außen.
Eine Lampe außen an der Fassade (6 cm vor der Außenfläche, 36 cm vor der
Raumkante bei 30 cm Wand) strahlt an dieser Linie vorbei, sobald der Strahl durch
die Ecke geht: das 30 × 30 cm große Eckstück wird von keiner Linie abgedeckt.
Möbel sind grundsätzlich keine Lichtblocker, also auch Säulen nicht.

**Lösung.**

* `Blocker` hat ein optionales `outline`. Für Wände ist das ihr Footprint aus
  `generateWalls()` (mit Gehrung, deckt die Ecke ab). `shadowed()` prüft nach
  der Mittellinie zusätzlich jede Kante des Umrisses, mit Höhe und Öffnungen wie
  bisher (die Kreuzung wird dafür auf die Wandachse projiziert). Liegt die Lampe
  selbst im Umriss (in die Wand eingelassen), gilt wie bisher nur die Linie.
* Säulen werden als Blocker in ihrer Lichtzone eingetragen: Möbeltyp mit
  `column`, `pillar` oder `saeule` als Namensteil (`columnOutline()`), Sockel
  höchstens 0,30 m. Runde Typen (`round`, `circle`, `rund`) als 16-Eck, alle
  anderen als gedrehtes Rechteck. Höhe = Montagehöhe + Höhe des Möbels.

**Tests.** `lighting.test.ts`: Lampe außen an einer 0,24 m dicken Wand, der Punkt
hinter der Ecke bleibt dunkel, der freie Punkt daneben hell; Säule wirft Schatten,
ein Sofa nicht, über eine niedrige Säule scheint das Licht hinweg.

### Eine Etage kann zur Etage darüber oder darunter gehören

**Problem.** Nicht jede Etage ist ein Stockwerk. Beispiel aus diesem Haus: Die
Garagen liegen 0,84 m tiefer als die Wohnung auf Straßenniveau und sind nur über
die Außentreppen erreichbar. Sie brauchen eine eigene Etage (sonst stünden sie auf
Wohnungshöhe), gehören aber zum selben Geschoss. Als eigene Etage werden sie in
der Hausansicht mit Abstand unter die Wohnung gezogen, beim Öffnen der Wohnung
abgedunkelt und 0,4 m abgesenkt (oder je nach Einstellung ausgeblendet), beim
Öffnen des Straßenniveaus fliegt die Wohnung weg, und das Etikett
„Straßenniveau · 2 Räume“ steht in der Hausansicht.

**Lösung.** Neues optionales Etagenfeld `attached`: `"above"` (gehört zur Etage
darüber), `"below"` (gehört zur Etage darunter) oder `null` (eigenes Stockwerk,
Standard). Im Editor unter den Etageneinstellungen: **Gehört zu: eigene Etage /
Etage darüber / Etage darunter** (nur bei mehr als einer Etage).

* `floorLevels()` in `model.ts` fasst Etagen zu Ebenen zusammen: Etage *i* und
  *i+1* (nach Höhe sortiert) bilden eine Ebene, wenn *i* `"above"` oder *i+1*
  `"below"` hat. Ketten sind erlaubt (Straßenniveau, Wohnung, Galerie über der
  Wohnung). Ohne Nachbarn auf der angegebenen Seite bleibt es eine eigene Ebene.
* `viewer3d.ts` `applyTargets()`: In der Hausansicht zählt der Abstand
  („Auseinander“) pro Ebene statt pro Etage. Wird eine Etage geöffnet, stehen alle
  Etagen ihrer Ebene an ihrem Platz und voll sichtbar; Etagen darüber und darunter
  verhalten sich wie bisher.
* `updateLabels()`: Eine verbundene Etage hat kein eigenes Etagen-Etikett.
* `schema.py` `FLOOR_SCHEMA`: `attached` = `None`, `"above"` oder `"below"`.
  Ein früher Stand dieses Forks speicherte `true`; das wird als `"above"`
  gelesen (Frontend `floorAttach()` und Schema).

**Tests.** `model.test.ts`: Ebenen für oben, unten, Kette, ohne Nachbarn und das
alte `true`; `tests/test_schema.py`: gültige Werte, `true` → `"above"`, ungültige
Werte werden abgelehnt.

### Lampen aus Möbel-Packs leuchten aus ihren leuchtenden Teilen

**Problem.** Bei einer Wandlaterne aus einem Pack (23,5 cm tief, Glaszylinder
13 cm vor der Wand) schwebt der Leuchtpunkt frei vor der Lampe.

**Ursache.** `buildHalos()` setzt den Halo jeder Lampe vom Typ `wall` auf
Mitte + Tiefe/2 + 5 cm nach vorn, auf halber Höhe; die Lichtquelle sitzt bei
Pack-Lampen auf 85 % der Höhe (`lightY`). Bei flachen Wandlampen passt das,
bei tiefen nicht.

**Lösung.** `glowCentre()` in `components/view3d.ts` nimmt die Mitte der Teile
mit `glow: true` (Begrenzungsquader in Breite, Tiefe und Höhe, gedreht und
gespiegelt wie das Möbel) und gibt sie als `lightAt` an den Viewer. Halo und
Lichtquelle sitzen dort. Packs ohne leuchtende Teile verhalten sich wie bisher.

### Regenwarnung mit eigener Schwelle (1.20.2.4)

**Problem.** Die Warnung „Fenster offen bei Regen“ lässt die Räume schon bei
leichtem Regen blinken. Gewünscht ist: Regen in 3D schon bei leichtem Regen,
die Warnung aber erst bei kräftigem Regen oder bei mäßigem Regen mit starkem
Wind (ein gekipptes Fenster bei Nieselregen ist kein Problem).

**Ursache.** `findAlerts()` in `frontend/src/alerts.ts` warnt, sobald es regnet:
nach `rain_entity` (eigene Wetterstation, > 0,1 mm/h oder an) oder nach dem
Zustand der Wetter-Entität (`rainy`, `pouring`, …). Dieselbe `rain_entity`
steuert auch den Regen in 3D (`weatherState()`). Eine Schwelle nur für die
Warnung lässt sich damit nicht setzen, ohne den Regen in 3D mit abzuschalten.

**Lösung.** Neue Einstellung `rain_warning_entity` (nur für die Warnung):

* Ist sie gesetzt und meldet sie etwas, entscheidet sie allein, ob ein offenes
  Fenster warnt: ein Binärsensor (an = warnen) oder eine Regenrate
  (über 0,1 mm/h), gelesen wie `rain_entity` über `stationRain()`.
* Meldet sie nichts (`unavailable`, `unknown`), gilt wie bisher `rain_entity`
  bzw. die Wetter-Entität. Der Schalter `rain_warning` schaltet die Warnung
  weiterhin ganz ab.
* Der Regen in 3D bleibt unberührt.
* Editor: unter „Warnung: Fenster offen bei Regen“ die Auswahl
  **Regenwarnung nur bei** (Binärsensoren und Regenquellen).
* `SETTINGS_SCHEMA`: `rain_warning_entity` (`None` oder Entity-ID).

Beispiel für die Entität (Trigger-Template, alle 10 Minuten aus der
met.no-Vorhersage der nächsten Stunde):

```yaml
- trigger:
    - trigger: time_pattern
      minutes: "/10"
    - trigger: homeassistant
      event: start
    - trigger: event
      event_type: event_template_reloaded
    - trigger: state
      entity_id: weather.forecast_home
  action:
    - action: weather.get_forecasts
      target:
        entity_id: weather.forecast_home
      data:
        type: hourly
      response_variable: vorhersage
  binary_sensor:
    - name: "Regenwarnung Fenster"
      unique_id: regenwarnung_fenster_metno
      state: >-
        {% set f = (vorhersage['weather.forecast_home'].forecast | default([]) | first) or {} %}
        {% set regen = f.precipitation | default(0) | float(0) %}
        {% set wind = f.wind_speed | default(0) | float(0) %}
        {{ regen >= 2.5 or (regen >= 1.0 and wind >= 39) }}
```

(kräftiger Regen ab 2,5 mm/h, mäßiger ab 1 mm/h, starker Wind ab 39 km/h =
Beaufort 6)

**Tests.** `alerts.test.ts`: leichter Regen mit eigener Entität aus → keine
Warnung, an → Warnung, `rain_warning` aus → keine, Entität `unavailable` →
wieder nach dem Regen; `tests/test_schema.py`: Standard `None`, Wert bleibt.

### Fensterbank pro Fenster und Rahmenlage in der Wand (1.20.2.5)

**Fensterbank.** Übernommen aus dem Original (Beta 1.25.0, Commit 1646030,
Issue #655): Feld `sill_board` (`auto` / `none` / `inside` / `outside`), Auswahl
im Fensterformular, Schema, Texte in allen Sprachen. Gleiches Datenformat wie im
Original, beim Update auf 1.25 geht nichts verloren.

**Rahmenlage.** Der feste Fensterrahmen sitzt im Original immer in der Mitte der
Wand (`viewer/openings.ts`: „fixed frame in the middle of the wall“). Bei
Fenstern in der Dämmebene (bündig mit der Außenwand, tiefe Laibung innen) steht
er damit eine halbe Wanddicke zu weit innen.

* Neues Feld `frame_pos` an Fenstern: `null`/`middle` (wie bisher), `outside`
  (Rahmen bündig mit der Außenseite), `inside` (bündig mit der Innenseite).
* `frameMid()` in `viewer/openings.ts` liefert die Rahmenebene; Flügel,
  Fensterbank innen und Festverglasung (`glass_wall`) folgen ihr. Türen und
  Garagentore bleiben in der Mitte, eine zu dünne Wand auch.
* Editor: „Rahmen in der Wand“ im Fensterformular. `OPENING_SCHEMA`:
  `frame_pos` (`None`, `middle`, `outside`, `inside`).
* Tests: `viewer/openings.test.ts` (Mitte, außen, innen, Tür, dünne Wand),
  `tests/test_schema.py`.

### Milchglas (1.20.2.6)

**Problem.** Fenster und Glastüren kennen nur klares Glas. Ein Bad- oder
Treppenhausfenster oder eine feste Scheibe unten in einer Fensterfront aus
Milchglas sieht in 3D durchsichtig aus.

**Lösung.** Neues Feld `frosted` an Öffnungen (Standard `false`). Ist es
gesetzt, zeichnet `buildOpeningParts()` die Scheiben (feste Scheibe, Flügel,
Glastür, Seitenteil, Glaswand) nicht als additives Glas, sondern als
undurchsichtige milchige Fläche im Rahmen-Buffer (`FROSTED`). Editor: Haken
„Milchglas“ im Öffnungsformular. `OPENING_SCHEMA`: `frosted`. Tests:
`tests/test_schema.py`.

### Geänderte Dateien

| Datei | Änderung |
|---|---|
| `frontend/src/viewer/lighting.ts` | `Blocker.outline`, `columnOutline()`, Umrissprüfung in `shadowed()`, Säulen als Blocker |
| `frontend/src/viewer/lighting.test.ts` | 2 Tests (Hausecke, Säule) |
| `frontend/src/model.ts` | `Floor.attached`, `FloorAttach`, `floorAttach()`, `floorLevels()`, `Settings.rain_warning_entity` |
| `frontend/src/model.test.ts` | 2 Tests (Ebenen, altes `true`) |
| `frontend/src/viewer/viewer3d.ts` | `levels()`, `applyTargets()`, `updateLabels()`, `lightAt` in `lightSources()` und `buildHalos()` |
| `frontend/src/components/view3d.ts` | `glowCentre()`, `lightAt` für Pack-Lampen |
| `frontend/src/components/editor.ts` | Auswahl „Gehört zu“ in den Etageneinstellungen, „Regenwarnung nur bei“ in den Wetter-Einstellungen |
| `frontend/src/i18n.ts` | Texte Deutsch und Englisch (`floor_attached*`, `rain_warning_entity*`) |
| `custom_components/neonplan3d/schema.py` | `attached` in `FLOOR_SCHEMA`, `rain_warning_entity` in `SETTINGS_SCHEMA` |
| `tests/test_schema.py` | 2 Tests |
| `frontend/src/alerts.ts`, `alerts.test.ts` | `rain_warning_entity` entscheidet die Fensterwarnung (1.20.2.4), 1 Test |
| `custom_components/neonplan3d/frontend/*.js`, `site/import/neonplan-import.js` | neu gebaut (`npm run build`) |
| `custom_components/neonplan3d/manifest.json` | Version 1.20.2.3, mit der Regenwarnung 1.20.2.4 |

Frontend: 415 Tests grün, `tsc --noEmit` sauber, alle Bundles im Budget
(`neonplan3d-3d.js` 780,0 von 780 KB, damit am Limit). Python: `tests/test_schema.py` 15 grün.

## Das Frontend bauen

Seit dem Fix in `earth.ts` gehört ein Frontend-Build dazu. Er ist
reproduzierbar: ohne eigene Änderungen kommen dieselben Bundles heraus, die
das Original ausliefert.

**Nicht im QNAP-Share bauen** (dort liegt das Repo, aber `npm` über SMB ist
langsam und die `node_modules` vertragen sich nicht zwischen Windows und
Linux). Stattdessen eine lokale Kopie:

```bash
# 1. frontend/, custom_components/neonplan3d/ und site/ lokal kopieren
# 2. dort:
cd frontend
npm ci
npm test            # 415 Tests
npm run typecheck
npm run build       # schreibt nach ../custom_components/neonplan3d/frontend/
# 3. die erzeugten *.js zurück ins Repo kopieren
```

`build.mjs` nimmt die Version aus `custom_components/neonplan3d/manifest.json`
und schreibt sie ins Bundle. Wer baut, braucht `--stamp` aus
`tools/fork_release.py` also nicht; das Skript bleibt für den Fall, dass nur
die Versionsnummer geändert wird.

## Die Python-Tests laufen lassen

Maßgeblich ist die CI (`.github/workflows/ci.yml`): Linux, Python 3.13,
`pip install -r requirements_test.txt ruff mypy`, dann `ruff check`,
`ruff format --check`, `mypy` und `pytest`. `requirements_test.txt` pinnt
`pytest-homeassistant-custom-component` **absichtlich nicht** — damit wird immer
gegen die aktuelle Home-Assistant-Version getestet, und ein Upstream-Merge zeigt
sofort, was eine neue HA-Version kaputt macht.

Die `2025.1.0` in `hacs.json` ist davon unberührt: das ist die Mindestversion, die
HACS prüft, nicht die Testversion. Wer ein venv mit HA 2025.1 baut, bekommt rund
30 Fehlschläge und ebenso viele Errors — nicht wegen des Forks, sondern weil die
Testfixtures von `pytest-homeassistant-custom-component` zur jeweiligen HA-Version
gehören. Gemessen am 2026-10-19: HA 2025.1.4 → 33 failed / 29 errors,
HA 2026.2.3 → 125 passed.

Unter Windows kommt Home Assistant nicht einmal durch den Import (`fcntl`,
`resource`). Was dafür nötig ist, steht in
[`tests/windows/README.md`](tests/windows/README.md) — kurz:

```bash
uv venv --python 3.13 "$HOME/.venvs/neonplan3d-test"   # HA verlangt >=3.13.2
export VIRTUAL_ENV="$HOME/.venvs/neonplan3d-test"
echo "lru-dict==1.4.1" > overrides.txt                 # HA pinnt 1.3.0, kein cp313-Wheel
uv pip install --override overrides.txt -r requirements_test.txt
PYTHONPATH="$(pwd);$(pwd)/tests/windows" "$HOME/.venvs/neonplan3d-test/Scripts/python.exe" -m pytest -p np3d_win_sockets -q
```

`scipy` und `trimesh` stehen in `requirements_test.txt`, weil die Geometrietests zu
`tools/mesh2pack.py` sich sonst selbst überspringen: 14 Tests, die stillschweigend
nichts prüfen.

## Heizkörper in eigener Farbe (2.0.0.3)

`settings.materials.radiator` (`"#rrggbb"`) färbt alle Heizkörper des Plans, ohne Angabe bleibt das eingebaute Neon-Blau.
Die Farbe wird in `setTerrain()` (model.ts) gemerkt, also an denselben Stellen wie der Boden gesetzt; `radiator()` in
`viewer/furniture.ts` liest sie über `radiatorColor()`.

## Mond an seiner echten Position (2.0.0.4)

Nachts stand die Mondscheibe bisher gegenüber der Sonne (Azimut + 180°, Höhe = Sonnentiefe, mindestens 10°).
Jetzt rechnet `frontend/src/moon.ts` (Näherung nach SunCalc, etwa 1° genau) Azimut und Höhe aus Breite und Länge
von Home Assistant (`hass.config`); unter dem Horizont gibt es keine Scheibe. Ohne Standort bleibt das alte Verhalten.

## Tür ohne Sensor ganz offen (2.0.0.5)

Neben `shut` (ohne Sensor geschlossen) gibt es `open_wide`: eine Tür ohne Kontakt wird ganz offen statt halb offen
gezeichnet. Feld in `schema.py` (Öffnung), `model.ts` und `devices.ts` (`wide`). Im Editor gibt es noch keinen Schalter,
das Feld wird im Plan gesetzt.

## Möbel ohne eigenen Ton (2.0.2.2)

`mute: true` an einem Möbel (Fernseher) zeigt dessen Media-Player weiter auf dem Bildschirm, aber Klang-Ringe und
Now-Playing-Karte kommen von den anderen Möbeln mit derselben Entity (Lautsprecher). Feld in `schema.py`, `model.ts`,
ausgewertet in `components/view3d.ts` (Klang & Kino). Kein Schalter im Editor.

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

Danach **immer** die Version in die Bundles stempeln:

```bash
python tools/fork_release.py --stamp
```

Warum: Das Frontend trägt seine Version als Konstante im gebauten Bundle. Das
Original liefert dort seine eigene Version, unser `manifest.json` hat die
vierte Stelle. Ohne Stempel vergleicht das Panel beide und fordert dauerhaft
zum Neuladen auf (`needs_reload` in `frontend/src/i18n.ts`). Der Stempel
schreibt die Version aus dem Manifest in `neonplan3d.js`, ohne das Frontend neu
zu bauen. Der Aufruf ist wiederholbar: ist schon gestempelt, passiert nichts.

**Konflikte sind in zwei Dateien zu erwarten:**

* `custom_components/neonplan3d/frontend/*.js` - die gebauten Bundles. Immer
  die Fassung des Originals nehmen
  (`git checkout --theirs custom_components/neonplan3d/frontend/`) und danach
  **neu bauen**, siehe oben. Nie von Hand in diesen Dateien editieren.
* `frontend/src/viewer/earth.ts`, wenn das Original an `coverAbove()` arbeitet.
  Sollte der Fehler dort behoben sein (Issue #602), kann unsere Fassung
  entfallen - dann prüft `earth.test.ts`, ob das Verhalten stimmt.
* `packs.py`, aber nur wenn das Original dort anfasst, was der Fork anfasst:
  die Importliste am Dateikopf, den Bereich um `STUDIO_KEYS` oder
  `verify_pack()`. Die eigenen Zeilen sind mit `FORK` markiert, also gilt beim
  Auflösen:

1. Die Änderung des Originals übernehmen.
2. Die mit `FORK` markierten Zeilen daneben wieder einsetzen. Wenn das Original
   `verify_pack()` umbaut, bleiben zwei Dinge zu tun: die lokalen Schlüssel zu
   den Herausgeber-Schlüsseln dazunehmen und die Beschränkung auf eigene Möbel
   nach `validate_payload()` prüfen.
3. Danach **`pytest tests/test_packs_fork.py`** und, im Frontend,
   **`npm test`** laufen lassen. Diese Tests sind
   der Beweis, dass der Fork noch tut, was er soll: wenn sie durchlaufen, sind
   eigene Möbel importierbar und Pro-Erweiterungen weiter gesperrt. Dazu
   `pytest tests/test_packs.py`, damit der Signaturweg des Originals heil ist.

Nach dem Merge die Version nachziehen und ein Release bauen, siehe unten.

### Wenn das Original ein Möbel-Studio bekommt

Dann ist dieser Fork überflüssig. Den Block in `packs.py` entfernen, zurück auf
das Original wechseln, die eigenen Packs mit dem Studio-Schlüssel neu
unterschreiben lassen.

### Bildschirme: Schein passend zur Größe (2.0.0.2)

**Problem.** Ein leuchtender Bildschirm bekommt einen Schein von 18 bis 30 cm rundherum, auch ein
Laptop oder Tablet von 25 cm Breite; der Schein ist dann größer als das Gerät.

**Lösung.** `buildScreens()` (`viewer/viewer3d.ts`): der Schein ist höchstens 40 % der kürzeren
Bildschirmseite breit und folgt dem `glow_scale` des Möbels (0 = kein Schein).

## Automatisch dem Original folgen

Der Workflow `.github/workflows/fork-sync.yml` läuft alle drei Stunden (und von Hand unter
*Actions → Fork sync → Run workflow*). `tools/fork_sync.py` holt die Tags des Originals und führt
dessen neuestes Release (`vX.Y.Z`) in `main` zusammen:

- Gebaute Dateien (Bundles, `site/import`) und die Workflows des Originals kommen bei einem Konflikt
  vom Original und werden neu gebaut; die Sprachdateien behalten die zusätzlichen Schlüssel des Forks.
- Version `X.Y.Z.1`, die eigenen Manifest-Felder (codeowners, documentation, issue_tracker), dann
  `npm ci`, Tests, Typprüfung und Build.
- Commit, Tag `vX.Y.Z.1`, Push und ein Release mit `neonplan3d.zip`. HACS zeigt das als Update.

Ein Konflikt in Quelltext oder ein roter Build bricht ab, ohne etwas zu veröffentlichen, und öffnet ein
Issue im Fork. HACS bietet dann einfach kein Update an und bleibt beim letzten guten Fork-Release.
Lokal testen: `python tools/fork_sync.py --dry-run` oder `--local` (zusammenführen ohne Build und Push).

Die Workflows des Originals (Discord, Pages, Shop-Check, Release) sind im Fork unter *Actions*
deaktiviert; sie würden hier nur scheitern.

## Version und Release

HACS installiert hier aus dem Release-Asset (`hacs.json`, `zip_release`).
Upstream baut das ZIP im Workflow `.github/workflows/release.yml` -
**in einem Fork laufen GitHub Actions aber erst, wenn man sie einmal von Hand
freigibt** (Reiter *Actions* im Repo). Solange das nicht passiert ist, baut
`tools/fork_release.py` das ZIP genauso und hängt es an:

```bash
# manifest.json: "version": "1.20.2.1"   (Original + vierte Stelle für den Fork)
python tools/fork_release.py --stamp
git commit -am "1.20.2.1: ..." && git push
gh release create v1.20.2.1 --repo d14tk/neonplan3d --title "1.20.2.1" --notes "..."
python tools/fork_release.py --tag v1.20.2.1
```

Nach einem Update muss die Seite im Browser einmal **hart** neu geladen werden
(in der Companion-App: Einstellungen → Companion-App → Frontend-Cache
zurücksetzen), sonst läuft dort das alte Bundle weiter.

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

## Merge-Hinweise (2.0.2.1)

- Die Bundle-Budgets des Forks stehen als Zuschlag `FORK_EXTRA` an der Pruefstelle in `frontend/build.mjs`, nicht in `BUDGET`. So kollidieren Budgetaenderungen des Originals nicht mehr.
- `hacs.json` bleibt beim Sync immer die des Forks (zip_release mit `neonplan3d.zip`).

