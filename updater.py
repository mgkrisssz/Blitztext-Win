"""
Update-Hinweis: fragt (hoechstens einmal pro Start, im Hintergrund) bei GitHub nach der
neuesten Release-Version. Es wird nichts installiert und nichts uebertragen ausser der
normalen Anfrage (IP-Adresse wie bei jedem Webseiten-Aufruf). Abschaltbar ueber
"update_check": false in config.json bzw. im Einstellungsfenster.
"""

import json
import re
import threading
import urllib.request

REPO = "mgkrisssz/Blitztext-Win"
API = "https://api.github.com/repos/%s/releases/latest" % REPO


def _version_tuple(text):
    """'v1.2.3' -> (1, 2, 3); Unverstaendliches -> None."""
    zahlen = re.findall(r"\d+", text or "")
    return tuple(int(z) for z in zahlen[:3]) if zahlen else None


def neuer(aktuell, gefunden):
    a, g = _version_tuple(aktuell), _version_tuple(gefunden)
    return bool(a and g and g > a)


def pruefen(aktuell, callback):
    """Im Hintergrund pruefen; callback(tag, url) nur, wenn es etwas Neueres gibt.
    Alle Fehler (kein Internet, kein Release, Limit) werden still geschluckt."""
    def _arbeit():
        try:
            req = urllib.request.Request(API, headers={
                "User-Agent": "Blitztext-Win-Update-Check",
                "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=8) as r:
                d = json.load(r)
            tag, url = d.get("tag_name") or "", d.get("html_url") or ""
            if tag and url.startswith("https://github.com/") and neuer(aktuell, tag):
                callback(tag, url)
        except Exception:
            pass
    threading.Thread(target=_arbeit, daemon=True).start()
