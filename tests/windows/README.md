# Die Tests unter Windows laufen lassen

Maßgeblich ist die CI: Linux, Python 3.13, `pip install -r requirements_test.txt`.
Home Assistant selbst unterstützt Windows seit Jahren nicht mehr, und das merkt man
schon beim Import: `homeassistant.runner` zieht `fcntl`, `homeassistant.util.resource`
zieht `resource` — beides gibt es nur auf POSIX. Dieses Verzeichnis ersetzt die zwei
Module durch das Minimum, das der Import braucht, und nimmt pytest-socket die Sperre ab,
die den Windows-Eventloop aussperrt.

Die Dateien gehören **nur** auf den `PYTHONPATH`, wenn man unter Windows testet. Auf
Linux würden `fcntl.py` und `resource.py` die echten Module verdecken; beide brechen
dort deshalb mit einem `ImportError` ab, statt still das Falsche zu tun.

## Einmal einrichten

Python **3.13** ist Pflicht: Home Assistant verlangt `>=3.13.2`.

```bash
uv venv --python 3.13 "$HOME/.venvs/neonplan3d-test"
export VIRTUAL_ENV="$HOME/.venvs/neonplan3d-test"
# HA pinnt lru-dict==1.3.0, davon gibt es kein cp313-Wheel für Windows, und ohne
# MS Visual C++ Build Tools baut es nicht. 1.4.1 bringt eines mit und ist kompatibel.
echo "lru-dict==1.4.1" > overrides.txt
uv pip install --override overrides.txt -r requirements_test.txt
```

Nicht im QNAP-Share anlegen — dort liegt das Repo, aber ein venv über SMB ist langsam
und vermischt sich mit den Linux-Installationen.

## Aufrufen

```bash
REPO=$(pwd)
PYTHONPATH="$REPO;$REPO/tests/windows" \
  "$HOME/.venvs/neonplan3d-test/Scripts/python.exe" -m pytest -p np3d_win_sockets -q
```

Das Repo-Root muss im `PYTHONPATH` stehen, sonst findet
`from custom_components.neonplan3d import packs` nichts.

## Wenn eine Hälfte der Suite rot ist

Dann steht fast immer eine zu alte Home-Assistant-Version im venv. `hacs.json` nennt
`2025.1.0`, das ist die **Mindestversion für HACS**, nicht die, gegen die der Code
getestet wird: `requirements_test.txt` pinnt `pytest-homeassistant-custom-component`
nicht, also gilt die jeweils aktuelle Version. Mit HA 2025.1.4 gemessen: 33 failed,
29 errors. Mit HA 2026.2.3: alles grün.
