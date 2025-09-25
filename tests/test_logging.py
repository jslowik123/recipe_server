#!/usr/bin/env python3
"""
Test script für das detaillierte Logging System
"""
import time
from detailed_logger import get_task_logger, finalize_task_log

def test_detailed_logging():
    """Testet alle Logging-Funktionen"""

    # Erstelle einen Test-Task-Logger
    test_task_id = f"test_task_{int(time.time())}"
    task_logger = get_task_logger(test_task_id)

    print(f"🧪 Teste Logging für Task-ID: {test_task_id}")

    # Test 1: Basic Logging
    task_logger.log("INFO", "Test gestartet", {
        "test_type": "functionality_test",
        "timestamp": time.time()
    })

    # Test 2: Step Logging
    task_logger.log_step(1, 5, "Initialisierung", {
        "services": ["test_service_1", "test_service_2"],
        "config": {"max_items": 10, "timeout": 30}
    })

    # Test 3: Progress Logging
    for i in range(1, 4):
        task_logger.log_progress(i, 3, "Verarbeite Test-Daten", {
            "current_item": f"item_{i}",
            "processing_time": 0.5
        })
        time.sleep(0.1)

    # Test 4: Raw Data Logging
    test_data = {
        "video_url": "https://example.com/test-video",
        "extracted_text": "Das ist ein Test-Text für das Logging-System.",
        "subtitles": ["Test Untertitel 1", "Test Untertitel 2"],
        "frames": [f"frame_{i}.jpg" for i in range(5)]
    }
    task_logger.log_raw_data("test_video_data", test_data)

    # Test 5: Error Logging
    try:
        # Simuliere einen Fehler
        raise ValueError("Das ist ein Test-Fehler für das Logging-System")
    except Exception as e:
        task_logger.log_error(e, "Test Error Handler", {
            "error_context": "simulated_error",
            "test_phase": "error_testing"
        })

    # Test 6: Success Logging
    task_logger.log_success("Test erfolgreich abgeschlossen", {
        "total_tests": 6,
        "all_passed": True,
        "execution_time": time.time()
    })

    # Test 7: Finalize Log
    finalize_task_log(test_task_id, "SUCCESS", {
        "test_type": "functionality_test",
        "tests_executed": 6,
        "all_tests_passed": True,
        "log_file_created": True
    })

    print(f"✅ Test abgeschlossen! Log-Datei: ./logs/{test_task_id}.txt")
    return test_task_id

if __name__ == "__main__":
    test_task_id = test_detailed_logging()

    # Zeige den Inhalt der erstellten Log-Datei
    print("\n" + "="*50)
    print("INHALT DER LOG-DATEI:")
    print("="*50)

    try:
        with open(f"./logs/{test_task_id}.txt", "r", encoding="utf-8") as f:
            print(f.read())
    except FileNotFoundError:
        print("❌ Log-Datei wurde nicht erstellt!")