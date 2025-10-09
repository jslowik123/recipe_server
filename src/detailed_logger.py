"""
Detaillierter Logger für TikTok Scraping Pipeline
Schreibt alle Logs mit task_id als Dateiname in txt-Dateien im lokalen Verzeichnis
"""
import os
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any
from threading import Lock

class DetailedFileLogger:
    """
    Detaillierter Logger, der alle Aktivitäten in eine txt-Datei mit task_id als Namen schreibt
    """

    def __init__(self, task_id: str, base_dir: str = "./logs"):
        self.task_id = task_id
        self.base_dir = base_dir

        # Erstelle Dateinamen mit Datum und Uhrzeit
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        self.log_file = os.path.join(base_dir, f"{task_id}_{timestamp}.txt")
        self.lock = Lock()

        # Erstelle logs Verzeichnis falls es nicht existiert
        os.makedirs(base_dir, exist_ok=True)

        # Initialisiere Log-Datei mit Header
        self._init_log_file()

    def _init_log_file(self):
        """Initialisiert die Log-Datei mit Header-Informationen"""
        with self.lock:
            with open(self.log_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write(f"DETAILLIERTES LOG FÜR TASK: {self.task_id}\n")
                f.write(f"ERSTELLT AM: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")

    def log(self, level: str, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Schreibt einen Log-Eintrag in die Datei

        Args:
            level: Log-Level (INFO, ERROR, WARNING, DEBUG)
            message: Haupt-Nachricht
            details: Zusätzliche Details als Dictionary
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

        log_entry = f"[{timestamp}] [{level}] {message}\n"

        if details:
            log_entry += "    Details:\n"
            for key, value in details.items():
                # Formatiere lange Werte
                if isinstance(value, str) and len(value) > 100:
                    log_entry += f"      {key}: {value[:100]}...\n"
                elif isinstance(value, (list, dict)):
                    log_entry += f"      {key}: {str(value)[:200]}...\n"
                else:
                    log_entry += f"      {key}: {value}\n"

        log_entry += "\n"

        with self.lock:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)

    def log_step(self, step_number: int, total_steps: int, step_name: str, details: Optional[Dict[str, Any]] = None):
        """Protokolliert einen Pipeline-Schritt"""
        message = f"SCHRITT {step_number}/{total_steps}: {step_name}"
        self.log("INFO", message, details)

    def log_error(self, error: Exception, context: str = "", additional_info: Optional[Dict[str, Any]] = None):
        """Protokolliert einen Fehler mit vollständigen Details"""
        import traceback

        error_details = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context,
            "full_traceback": traceback.format_exc()
        }

        if additional_info:
            error_details.update(additional_info)

        self.log("ERROR", f"FEHLER in {context}", error_details)

    def log_success(self, message: str, result_summary: Optional[Dict[str, Any]] = None):
        """Protokolliert erfolgreiche Abschlüsse"""
        self.log("SUCCESS", message, result_summary)

    def log_progress(self, current: int, total: int, operation: str, details: Optional[Dict[str, Any]] = None):
        """Protokolliert Fortschritt bei längeren Operationen"""
        percentage = (current / total) * 100 if total > 0 else 0
        message = f"FORTSCHRITT: {operation} ({current}/{total} - {percentage:.1f}%)"
        self.log("PROGRESS", message, details)

    def log_raw_data(self, data_type: str, data: Any):
        """Protokolliert rohe Daten vollständig"""
        self.log("DATA", f"ROHDATEN ({data_type})", {
            "data_type": data_type,
            "data_size": len(str(data)) if data else 0,
            "data_content": str(data)
        })

    def finalize_log(self, final_status: str, summary: Optional[Dict[str, Any]] = None):
        """Schließt das Log mit einer Zusammenfassung ab"""
        with self.lock:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write(f"TASK ABGESCHLOSSEN: {final_status}\n")
                f.write(f"BEENDET AM: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                if summary:
                    f.write("ZUSAMMENFASSUNG:\n")
                    for key, value in summary.items():
                        f.write(f"  {key}: {value}\n")
                f.write("=" * 80 + "\n")


class TaskLogger:
    """
    Globaler Task Logger Manager
    Verwaltet Logger-Instanzen für verschiedene Tasks
    """

    _loggers: Dict[str, DetailedFileLogger] = {}
    _lock = Lock()

    @classmethod
    def get_logger(cls, task_id: str) -> DetailedFileLogger:
        """Holt oder erstellt einen Logger für eine Task-ID"""
        with cls._lock:
            if task_id not in cls._loggers:
                cls._loggers[task_id] = DetailedFileLogger(task_id)
            return cls._loggers[task_id]

    @classmethod
    def remove_logger(cls, task_id: str):
        """Entfernt einen Logger nach Task-Abschluss"""
        with cls._lock:
            if task_id in cls._loggers:
                del cls._loggers[task_id]


# Convenience-Funktionen für einfache Verwendung
def get_task_logger(task_id: str) -> DetailedFileLogger:
    """Holt einen Task-Logger"""
    return TaskLogger.get_logger(task_id)

def log_task_info(task_id: str, message: str, details: Optional[Dict[str, Any]] = None):
    """Schnelle Info-Log-Funktion"""
    TaskLogger.get_logger(task_id).log("INFO", message, details)

def log_task_error(task_id: str, error: Exception, context: str = ""):
    """Schnelle Error-Log-Funktion"""
    TaskLogger.get_logger(task_id).log_error(error, context)

def finalize_task_log(task_id: str, status: str, summary: Optional[Dict[str, Any]] = None):
    """Schließt das Task-Log ab und bereinigt"""
    logger = TaskLogger.get_logger(task_id)
    logger.finalize_log(status, summary)
    TaskLogger.remove_logger(task_id)