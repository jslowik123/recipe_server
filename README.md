# Rezept-Extraktions Backend

Backend-API für eine Mobile App, die automatisch Rezepte aus TikTok-Videos extrahiert. Die App sendet eine TikTok-URL, das Backend analysiert das Video mit KI und liefert strukturierte Rezeptdaten zurück.

## Funktionsweise

Das System extrahiert automatisch aus TikTok-Kochvideos:
- Zutatenliste
- Schritt-für-Schritt Anleitung
- Metadaten (Kochzeit, Portionen, etc.)
- Video-Thumbnail

Die Analyse erfolgt durch GPT-4 Vision, das einzelne Frames des Videos auswertet.

## Tech Stack

- **FastAPI** - REST API und WebSocket Server
- **Celery + Redis** - Asynchrone Task-Queue für Video-Verarbeitung
- **OpenAI GPT-4 Vision** - KI-gestützte Rezept-Extraktion
- **Supabase** - Datenbank und File Storage
- **Docker Compose** - Container-Orchestrierung
- **OpenCV** - Video-Frame-Extraktion

## Ablauf

1. Mobile App sendet TikTok-URL an `/scrape/async` Endpoint
2. Celery Worker lädt Video über Apify herunter
3. Key-Frames werden aus dem Video extrahiert (OpenCV)
4. Frames werden an GPT-4 Vision mit Rezept-Prompt gesendet
5. KI-Response wird in strukturiertes Rezept-Format geparst
6. Rezept wird in Datenbank gespeichert
7. Rezept-ID wird an App zurückgegeben

Live-Updates während der Verarbeitung über WebSocket-Verbindung.

## Schnellstart

```bash
# Dependencies installieren
pip install -r requirements.txt

# Umgebungsvariablen konfigurieren
cp .env.example .env
# API-Keys in .env eintragen

# Services starten
./scripts/setup-infra.sh
./scripts/deploy-app.shwas 
```
## API-Nutzung

**Scraping starten:**
```bash
POST /scrape/async
{
  "url": "https://www.tiktok.com/@user/video/123",
  "language": "de"
}
```

**Status abfragen:**
```bash
GET /task/{task_id}
```

**Live-Updates:**
```
WebSocket: /wss/{task_id}?token={jwt}
```

## Projekt-Struktur

```
src/
├── main.py              # FastAPI Applikation
├── tasks.py             # Celery Task-Definitionen
├── services.py          # Service-Layer (Apify, OpenAI, Supabase)
├── tiktok_scraper.py    # Haupt-Scraping-Logik
└── websocket_manager.py # WebSocket-Handler
```

## Docker-Architektur

Das System läuft produktiv auf einem VPS mit Docker Compose und besteht aus mehreren Services:

**Infrastructure Stack** (`docker-compose.infrastructure.yml`):
- **Redis** - Message Broker für Celery und Pub/Sub für WebSockets
- **Persistenz** - Redis Volumes für Queue-State

**Application Stack** (`docker-compose.app.yml`):
- **FastAPI Server** - REST API und WebSocket Endpoints
- **Celery Worker** - Video-Verarbeitung und KI-Analyse
- **Nginx** - Reverse Proxy mit WebSocket-Support

Alle Services sind über Docker Networks verbunden. Redis dient sowohl als Celery Message Broker für asynchrone Tasks als auch für WebSocket Pub/Sub zum Broadcasting von Progress-Updates.

**CI/CD**: GitHub Actions deployed automatisch auf den VPS bei jedem Push auf `main`.

## Anforderungen

- Python 3.11+
- Docker & Docker Compose
- OpenAI API Key
- Apify API Token
- Supabase Projekt
- VPS mit Docker (für Production)
