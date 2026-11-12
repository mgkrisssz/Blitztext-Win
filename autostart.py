"""
Autostart: legt eine kleine .vbs im Windows-Startordner an bzw. entfernt sie.
Wird vom Tray-Menue, vom Einstellungsfenster und von setup.bat genutzt
(einzige Stelle fuer diese Logik).

Kommandozeile:  python autostart.py on|off
"""

import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STARTUP_VBS = os.path.join(
    os.environ.get("APPDATA", ""), "Microsoft", "Windows",
    "Start Menu", "Programs", "Startup", "Blitztext-Autostart.vbs")


def enabled():
    return os.path.exists(STARTUP_VBS)


def set_enabled(on):
    """Autostart an/aus. Gibt True zurueck, wenn der Zustand jetzt stimmt."""
    try:
        if on and not enabled():
            launcher = os.path.join(APP_DIR, "Blitztext.vbs")
            # VBS liest Windows-ANSI, nicht UTF-8 (Umlaute im Benutzerordner!)
            with open(STARTUP_VBS, "w", encoding="mbcs") as f:
                f.write('CreateObject("WScript.Shell").Run '
                        '"wscript.exe ""%s""", 0, False\n' % launcher)
            print("[Blitztext] Autostart: AN")
        elif not on and enabled():
            os.remove(STARTUP_VBS)
            print("[Blitztext] Autostart: AUS")
        return enabled() == bool(on)
    except Exception as e:
        print(f"[Warnung] Autostart: {e}")
        return False


if __name__ == "__main__":
    arg = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if arg in ("on", "off"):
        sys.exit(0 if set_enabled(arg == "on") else 1)
    print("Aufruf: python autostart.py on|off")
    sys.exit(2)
