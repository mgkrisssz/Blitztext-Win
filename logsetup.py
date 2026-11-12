"""
Protokoll fuer Blitztext: schreibt alle Meldungen in blitztext.log (neben dem Programm),
wenn die App ohne Konsolenfenster laeuft (Blitztext.vbs / pythonw). Bei start_test.bat
bleibt die Ausgabe im Konsolenfenster.

Zusaetzlich faengt faulthandler harte Abstuerze (z. B. in nativen Bibliotheken) ab und
schreibt den Stack ins Protokoll - sonst verschwindet Blitztext spurlos.
Das Protokoll wird bei ueber 1 MB rotiert (blitztext.log.1), bleibt also klein.
"""

import os
import sys
import time
import faulthandler

MAX_BYTES = 1_000_000
_datei = None          # offen halten, sonst funktioniert faulthandler nicht


def log_pfad(app_dir):
    return os.path.join(app_dir, "blitztext.log")


def start(app_dir):
    global _datei
    pfad = log_pfad(app_dir)
    try:
        if os.path.exists(pfad) and os.path.getsize(pfad) > MAX_BYTES:
            alt = pfad + ".1"
            if os.path.exists(alt):
                os.remove(alt)
            os.replace(pfad, alt)
        _datei = open(pfad, "a", encoding="utf-8", buffering=1)
        _datei.write("\n===== Start %s =====\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
        faulthandler.enable(_datei, all_threads=True)
        # Ohne Konsole (pythonw) gibt es kein stdout -> in die Datei umleiten
        if sys.stdout is None or not sys.stdout.isatty():
            sys.stdout = _datei
            sys.stderr = _datei
    except Exception:
        pass       # Protokoll ist nice-to-have, nie ein Grund, die App nicht zu starten
