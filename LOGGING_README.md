# Detailliertes Logging System

Das TikTok Scraper System verfügt jetzt über ein umfassendes Logging-System, das alle Aktivitäten detailliert in txt-Dateien protokolliert.

## 🎯 Features

- **Task-basierte Logs**: Jede Task erstellt eine eigene Log-Datei mit der task_id als Dateiname
- **Vollständige Nachverfolgung**: Alle Schritte, Fehler, Daten und Ergebnisse werden protokolliert
- **Deutsche Sprache**: Logs sind auf Deutsch für bessere Verständlichkeit
- **Strukturierte Daten**: Details werden als Key-Value-Paare gespeichert
- **Thread-sicher**: Gleichzeitiges Schreiben von mehreren Tasks ist möglich

## 📁 Log-Dateien

Alle Log-Dateien werden im `./logs/` Verzeichnis gespeichert:
- Format: `{task_id}.txt`
- Encoding: UTF-8
- Struktur: Zeitstempel + Level + Nachricht + Details

## 📋 Log-Levels

- **INFO**: Normale Informationen über Pipeline-Schritte
- **ERROR**: Fehler mit vollständigem Traceback
- **SUCCESS**: Erfolgreiche Abschlüsse
- **PROGRESS**: Fortschritts-Updates bei längeren Operationen
- **DATA**: Vollständige Rohdaten (Apify-Ergebnisse, OpenAI-Responses, etc.)

## 🔧 Verwendung

### Automatisches Logging in Tasks
Das Logging ist vollständig in die bestehende Celery-Task-Pipeline integriert:

```python
@celery_app.task(bind=True)
def scrape_tiktok_async(self, post_url: str, language: str):
    task_id = self.request.id
    task_logger = get_task_logger(task_id)

    # Logs werden automatisch geschrieben
    task_logger.log("INFO", "Task gestartet", {"url": post_url})
```

### Manuelles Logging
```python
from detailed_logger import get_task_logger, finalize_task_log

# Logger für Task holen
task_logger = get_task_logger("meine_task_id")

# Verschiedene Log-Typen
task_logger.log("INFO", "Nachricht", {"detail1": "wert1"})
task_logger.log_step(1, 5, "Schritt-Name", {"config": "werte"})
task_logger.log_error(exception, "Kontext")
task_logger.log_raw_data("daten_typ", rohe_daten)
task_logger.log_success("Erfolgreich", {"summary": "info"})

# Log abschließen
finalize_task_log("meine_task_id", "SUCCESS", {"zusammenfassung": "daten"})
```

## 📊 Was wird geloggt?

### TikTok Scraping Pipeline
1. **Task-Start**: URL, Sprache, Konfiguration
2. **Apify-Scraping**: API-Calls, Antworten, Dataset-IDs
3. **Video-Verarbeitung**: Text-Extraktion, Untertitel, Frames
4. **OpenAI-Processing**: Input-Daten, API-Responses, generierte Rezepte
5. **Fehlerbehandlung**: Vollständige Tracebacks, Kontext-Informationen
6. **Ergebnisse**: Finale Daten, Zusammenfassungen

### Beispiel-Log-Struktur
```
================================================================================
DETAILLIERTES LOG FÜR TASK: abc123def456
ERSTELLT AM: 2025-09-14 18:39:43
================================================================================

[2025-09-14 18:39:43.191] [INFO] 🚀 TASK GESTARTET
    Details:
      task_id: abc123def456
      post_url: https://tiktok.com/@user/video/123
      language: de
      max_frames: 20

[2025-09-14 18:39:43.192] [INFO] SCHRITT 1/5: Initialisiere TikTok Scraper
    Details:
      url: https://tiktok.com/@user/video/123
      language: de
      service_config: TikTokScraper mit max_frames=20

[... weitere Logs ...]

================================================================================
TASK ABGESCHLOSSEN: SUCCESS
BEENDET AM: 2025-09-14 18:40:15
ZUSAMMENFASSUNG:
  url: https://tiktok.com/@user/video/123
  language: de
  result_status: SUCCESS
  has_recipe: True
================================================================================
```

## 🧪 Test

Das System kann mit dem Test-Skript getestet werden:

```bash
python3 test_logging.py
```

Dies erstellt eine vollständige Test-Log-Datei mit allen Logging-Features.

## ⚙️ Konfiguration

- **Log-Verzeichnis**: Standardmäßig `./logs/` (automatisch erstellt)
- **Datei-Format**: `{task_id}.txt`
- **Thread-sicher**: Ja, mit Threading-Locks
- **Automatische Bereinigung**: Logger werden nach Task-Abschluss automatisch entfernt

## 🔍 Debugging

Bei Problemen:
1. Prüfen Sie, ob das `./logs/` Verzeichnis existiert und beschreibbar ist
2. Überprüfen Sie die task_id in den Celery-Tasks
3. Schauen Sie in die Log-Datei für detaillierte Fehlerinformationen
4. Verwenden Sie `test_logging.py` um das System zu testen