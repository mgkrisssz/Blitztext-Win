# Datenschutz / Privacy

**Kurz:** Blitztext läuft komplett auf deinem PC. Es gibt kein Konto, keinen Server von uns und keine Telemetrie.
Deine Sprache und deine Texte verlassen den Rechner nicht.

*In short: everything runs on your PC. No account, no backend of ours, no telemetry. Your voice and your text never leave the machine.*

## Was wohin geht

| Was | Wohin | Wann |
|---|---|---|
| Sprache → Text (Whisper) | nur dein PC | immer, lokal auf GPU oder CPU |
| Sprachmodell herunterladen | Hugging Face (`huggingface.co`) | einmalig pro Modell, beim ersten Nutzen |
| Update-Hinweis | GitHub (`api.github.com`) | beim Start, abschaltbar (`update_check`) |
| Programmpakete installieren | PyPI (`pypi.org`) | nur während `setup.bat` |

Bei den Abfragen sehen die Anbieter wie bei jedem Webseiten-Aufruf deine IP-Adresse. Es werden **keine**
Aufnahmen, Texte oder Einstellungen gesendet.

## Was auf deinem PC gespeichert wird
- `config.json` – deine Einstellungen
- `woerterbuch.txt` – dein Wörterbuch
- `blitztext.log` – Protokoll für die Fehlersuche (Meldungen der App, auch erkannte Texte; wird bei 1 MB rotiert).
  **Wenn du ein Protokoll öffentlich teilst (z. B. in einem Issue), prüfe vorher, ob private Texte darin stehen.**
- Das Sprachmodell im Hugging-Face-Cache (`%USERPROFILE%\.cache\huggingface`)
- Der Verlauf der letzten 10 Diktate liegt nur im Arbeitsspeicher und ist nach dem Beenden weg.
- **Aufnahmen werden nicht gespeichert.** Das Mikrofon bleibt zwar geöffnet (Option `dauerhaft_offen`, damit der
  Start sofort geht), Audio wird aber nur **während einer Aufnahme** gesammelt und danach verworfen.

## Zwischenablage
Zum Einfügen legt Blitztext den Text kurz in die Zwischenablage und drückt Strg+V. Auf Wunsch (Einstellung
„Zwischenablage zurücksetzen“, standardmäßig aus) stellt es danach wieder her, was vorher darin war (nur Text). Der Windows-Zwischenablageverlauf (Win+V), falls
eingeschaltet, kann den diktierten Text trotzdem aufnehmen – das ist eine Windows-Funktion.

## Abschalten
- Update-Abfrage: Einstellungen → System → „Nach Updates suchen“ aus, oder `"update_check": false`.
- Komplett offline: Modell einmal laden, danach funktioniert Blitztext ohne Internet.
