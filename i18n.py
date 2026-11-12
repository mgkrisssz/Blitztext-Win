"""
Oberflaechen-Sprache (Deutsch / Englisch).

Die deutschen Texte sind zugleich die Schluessel: t("Mit Windows starten") liefert im
deutschen Modus den Text unveraendert und im englischen die Uebersetzung aus EN.
Fehlt eine Uebersetzung, bleibt der deutsche Text stehen (nie ein Absturz).

cfg["ui_language"]: "auto" (Windows-Sprache), "de" oder "en".
Neue Sprache? Eine weitere Tabelle wie EN anlegen und in TABELLEN eintragen.
"""

import ctypes

EN = {
    # --- Einstellungsfenster: Abschnitte
    "HOTKEYS": "HOTKEYS",
    "AUFNAHME": "RECORDING",
    "MIKROFON": "MICROPHONE",
    "MODELL": "MODEL",
    "SPRACHE": "LANGUAGE",
    "AUSGABE": "OUTPUT",
    "SYSTEM": "SYSTEM",
    "DARSTELLUNG": "APPEARANCE",
    # --- Hotkeys
    "Aufnahme": "Recording",
    "Erkennung": "Recognition",
    "Ausgabe": "Output",
    "Zweitsprache (einmalig)": "Second language (one-off)",
    "klicken, dann neue Taste drücken (Entf = aus)": "click, then press the new key (Del = off)",
    "Sprache, die der Zweit-Hotkey für ein Diktat nutzt": "Language the second hotkey uses for one dictation",
    "Taste drücken …": "Press a key …",
    "Entf hier nicht möglich": "Del not possible here",
    "Taste nicht unterstützt": "Key not supported",
    "nur mit Strg/Alt kombinieren": "only combine with Ctrl/Alt",
    "ungültig": "invalid",
    "aus": "off",
    "Hotkey": "Hotkey",
    "Esc = verwerfen": "Esc = discard",
    # --- Aufnahme
    "Gedrückt halten (Push-to-Talk)": "Hold to talk (push-to-talk)",
    "Hotkey halten = aufnehmen · loslassen = fertig": "hold hotkey = record · release = done",
    "Ton bei Start/Stopp": "Beep on start/stop",
    # --- Mikrofon
    "Automatisch (System-Standard)": "Automatic (system default)",
    "Pegel": "Level",
    # --- Modell
    "Wechsel lädt das Modell neu · beim ersten Mal Download": "switching reloads the model · first use downloads it",
    "Tiny – winzig, ungenau": "Tiny – very small, rough",
    "Base – sehr schnell": "Base – very fast, basic",
    "Small – schnell, gut (CPU)": "Small – fast, good (CPU ok)",
    "Medium – genauer, mehr Power": "Medium – more accurate",
    "Turbo – fast wie Large, schneller": "Turbo – near-Large, faster",
    "Large-v3 – beste Qualität (GPU)": "Large-v3 – best quality (GPU)",
    # --- Sprache
    "Ins Englische übersetzen": "Translate to English",
    # --- Ausgabe
    "Automatisch einfügen": "Paste automatically",
    "Automatisch Enter (absenden)": "Press Enter automatically (send)",
    "Tippen statt Einfügen": "Type instead of paste",
    "Sprachbefehle": "Voice commands",
    "Tipp-Tempo: Sofort": "Typing speed: instant",
    "Tipp-Tempo: Schnell": "Typing speed: fast",
    "Tipp-Tempo: Normal": "Typing speed: normal",
    "Tipp-Tempo: Langsam": "Typing speed: slow",
    "Wie schnell der Text beim Tippen erscheint.": "How fast the text appears when typing.",
    "Zwischenablage zurücksetzen": "Restore clipboard",
    "nach dem Einfügen ist wieder dein vorher Kopiertes drin": "after pasting, what you copied before is back",
    "»neue Zeile« / »neuer Absatz« sprechen = Umbruch": "say “new line” / “new paragraph” = line break",
    # --- System
    "Mit Windows starten": "Start with Windows",
    "Status-HUD anzeigen": "Show status HUD",
    "wirkt nach Neustart der App": "takes effect after restarting the app",
    "Nach Updates suchen": "Check for updates",
    "fragt gelegentlich bei GitHub nach einer neuen Version": "occasionally asks GitHub for a new version",
    # --- Darstellung
    "Sprache der Oberfläche": "Interface language",
    "Automatisch": "Automatic",
    "Hell": "Light",
    "Wörterbuch bearbeiten": "Edit dictionary",
    # --- Erklaerungen (Maus ueber der Zeile)
    'Startet und beendet die Aufnahme.': 'Starts and stops recording.',
    'Diktiert einmalig in der Zweitsprache.': 'Dictates once in the second language.',
    'Sprache des Zweit-Hotkeys.': 'Language of the second hotkey.',
    'Halten = aufnehmen, loslassen = fertig.': 'Hold = record, release = done.',
    'Piepton bei Start und Ende.': 'Beep at start and end.',
    'Der Pegel darunter muss beim Sprechen ausschlagen.': 'The level below must move when you speak.',
    'Größer = genauer, aber langsamer.': 'Bigger = more accurate, but slower.',
    'Die Sprache, in der du sprichst.': 'The language you speak.',
    'Schreibt alles direkt auf Englisch.': 'Writes everything directly in English.',
    'Fügt den Text am Cursor ein.': 'Pastes the text at your cursor.',
    'Dein vorher Kopiertes bleibt erhalten.': 'Keeps what you copied before.',
    'Drückt nach dem Einfügen Enter.': 'Presses Enter after pasting.',
    'Wie von Hand getippt. Nur nötig, wenn Einfügen nicht klappt.': 'Typed as by hand. Only needed if pasting does not work.',
    '„neue Zeile“ wird zum Umbruch.': '“new line” becomes a line break.',
    'Startet mit deiner Anmeldung.': 'Starts when you sign in.',
    'Anzeige am Bildschirmrand beim Aufnehmen.': 'Display at the screen edge while recording.',
    'Fragt bei GitHub nach einer neuen Version.': 'Asks GitHub for a new version.',
    'Sprache der Menüs.': 'Language of the menus.',
    'Namen und feste Ersetzungen (falsch => richtig).': 'Names and fixed replacements (wrong => right).',
    'Beendet Blitztext und startet es neu.': 'Quits and restarts Blitztext.',
    # --- Sprachen (Anzeigenamen)
    "Deutsch": "German", "Englisch": "English", "Ungarisch": "Hungarian",
    "Französisch": "French", "Spanisch": "Spanish", "Italienisch": "Italian",
    "Portugiesisch": "Portuguese", "Niederländisch": "Dutch", "Polnisch": "Polish",
    "Tschechisch": "Czech", "Türkisch": "Turkish", "Russisch": "Russian",
    "Ukrainisch": "Ukrainian", "Arabisch": "Arabic", "Japanisch": "Japanese",
    "Chinesisch": "Chinese",
    # --- Tray-Menue
    "Einstellungen ...": "Settings ...",
    "Status": "Status",
    "Mikrofon": "Microphone",
    "Sprache": "Language",
    "Verlauf (klick = kopieren)": "History (click = copy)",
    "(noch nichts diktiert)": "(nothing dictated yet)",
    "Wörterbuch": "Dictionary",
    "Mikrofonliste aktualisieren": "Refresh microphone list",
    "Protokoll öffnen": "Open log file",
    "Beenden": "Quit",
    "Neu starten": "Restart",
    "Update verfügbar": "Update available",
    # --- Tooltips / HUD
    "Blitztext - Modell wird geladen ...": "Blitztext - loading model ...",
    "Blitztext - bereit": "Blitztext - ready",
    "Blitztext - HOERE ZU ... (Hotkey = fertig, Esc = verwerfen)": "Blitztext - LISTENING ... (hotkey = done, Esc = discard)",
    "Blitztext - verarbeite ...": "Blitztext - processing ...",
    "Blitztext - Fehler": "Blitztext - error",
    "Höre zu …": "Listening …",
    "Verarbeite …": "Processing …",
    "(nichts erkannt)": "(nothing recognized)",
    "Modell wird geladen …": "Loading model …",
    "Modell wird heruntergeladen": "Downloading model",
    "Bereit – drücke {key} zum Diktieren": "Ready – press {key} to dictate",
    "Willkommen! Das Modell wird einmalig geladen.": "Welcome! The model is loaded once.",
    "Modell konnte nicht geladen werden – Internet?": "Could not load model – internet?",
    "Neue Version {tag} verfügbar": "New version {tag} available",
}

TABELLEN = {"en": EN}
_sprache = "de"


def system_sprache():
    """'de', wenn Windows auf Deutsch laeuft, sonst 'en'."""
    try:
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "de" if (lang_id & 0x3FF) == 0x07 else "en"
    except Exception:
        return "en"


def set_language(code):
    """'auto', 'de' oder 'en' setzen."""
    global _sprache
    if code not in ("de", "en"):
        code = system_sprache()
    _sprache = code


def current():
    return _sprache


def t(text):
    """Text in der aktuellen Oberflaechen-Sprache (Schluessel = deutscher Text)."""
    tabelle = TABELLEN.get(_sprache)
    if not tabelle:
        return text
    return tabelle.get(text, text)
