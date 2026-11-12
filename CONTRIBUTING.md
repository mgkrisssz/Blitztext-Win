# Mitmachen / Contributing

Schön, dass du mithelfen willst! Das hier ist ein kleines Hobbyprojekt – Antworten können etwas dauern.

## Fehler melden
Bitte ein [Issue](../../issues/new/choose) aufmachen mit: Windows-Version, Python-Version, GPU (NVIDIA / AMD / keine),
gewähltes Modell und den letzten Zeilen aus `blitztext.log` (Tray-Menü → „Protokoll öffnen“).
Bitte vorher prüfen, ob private Texte im Protokoll stehen.

## Code beitragen
1. Repo forken, Branch anlegen.
2. `setup.bat` ausführen, mit `start_test.bat` testen.
3. Kleine, in sich geschlossene Änderungen sind am einfachsten zu prüfen. Neue Texte der Oberfläche gehören in
   `i18n.py` (Deutsch ist der Schlüssel, die englische Übersetzung der Wert).
4. Pull Request mit kurzer Beschreibung: was, warum, wie getestet.

Mit deinem Beitrag stimmst du zu, dass er unter der [MIT-Lizenz](LICENSE) des Projekts steht.

## Ideen
Wünsche (z. B. eine `.exe`, AMD-/Intel-Beschleunigung, weitere Sprachen der Oberfläche) bitte als Issue schreiben –
je mehr Leute sich melden, desto eher wird es gebaut.
