# Infrastruktur-Dokumentation: ResiMply.app

## Überblick

Diese Dokumentation beschreibt die komplette Infrastruktur der TikTok-Rezept-Scraping-Anwendung, die unter **resimply.app** läuft.

## Systemarchitektur

```
┌─────────────────────────────────────────────────────────────────┐
│                          Internet                                │
│                     (resimply.app)                               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         │ HTTPS (443) / HTTP (80)
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                          VPS Server                              │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           Nginx Reverse Proxy + SSL                      │   │
│  │  - Automatische SSL-Zertifikate (Let's Encrypt)         │   │
│  │  - WebSocket-Unterstützung                               │   │
│  │  - Load Balancing                                         │   │
│  └─────────────────┬───────────────────────────────────────┘   │
│                    │                                             │
│                    ├─────────────────────────────────┐          │
│                    │                                  │          │
│                    ▼                                  ▼          │
│  ┌──────────────────────────┐    ┌─────────────────────────┐  │
│  │   FastAPI Web Server     │    │   Celery Worker         │  │
│  │   (uvicorn)              │    │   (Asynchrone Tasks)    │  │
│  │   - REST API             │    │   - TikTok Scraping     │  │
│  │   - WebSocket Server     │    │   - Video-Verarbeitung  │  │
│  │   - JWT Auth             │    │   - AI-Verarbeitung     │  │
│  └──────────────┬───────────┘    └──────────┬──────────────┘  │
│                 │                             │                  │
│                 └──────────┬──────────────────┘                 │
│                            │                                     │
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                    Redis Server                          │  │
│  │  - Task Queue (Celery Broker)                           │  │
│  │  - Task Results (Celery Backend)                        │  │
│  │  - Pub/Sub für WebSocket-Updates                        │  │
│  │  - Passwortgeschützt (127.0.0.1)                        │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                            │
                            │ API Calls
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Externe Services                              │
│                                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │   Apify     │  │   OpenAI     │  │   Supabase         │    │
│  │   (Scraper) │  │   (GPT-4)    │  │   (Database/Auth)  │    │
│  └─────────────┘  └──────────────┘  └────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Komponenten-Details

### 1. Infrastructure Layer (docker-compose.infrastructure.yml)

#### 1.1 Nginx Reverse Proxy
- **Image:** `nginxproxy/nginx-proxy:latest`
- **Container:** `nginx-proxy`
- **Ports:**
  - `80:80` (HTTP, automatischer Redirect zu HTTPS)
  - `443:443` (HTTPS mit SSL)
- **Funktionen:**
  - Automatisches Reverse Proxying zu Backend-Services
  - WebSocket-Unterstützung für Echtzeit-Updates
  - Virtuelle Hosts basierend auf Docker-Container-Labels
  - SSL-Termination

**Konfiguration:**
```nginx
location /wss/ {
    proxy_pass http://web:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_read_timeout 3600s;  # 60 Minuten für lange Verbindungen
}
```

#### 1.2 Let's Encrypt Companion
- **Image:** `nginxproxy/acme-companion:latest`
- **Container:** `nginx-letsencrypt`
- **Funktionen:**
  - Automatische SSL-Zertifikatserstellung
  - Automatische Zertifikatserneuerung (alle 60 Tage)
  - ACME Challenge Handling
  - Integration mit Nginx-Proxy

**Umgebungsvariablen:**
- `DEFAULT_EMAIL`: Kontakt-E-Mail für Let's Encrypt
- `NGINX_PROXY_CONTAINER`: Referenz zum Nginx-Container

#### 1.3 Redis Server
- **Image:** `redis:7-alpine`
- **Container:** `redis-server`
- **Port:** `127.0.0.1:6379` (nur localhost)
- **Funktionen:**
  - Celery Message Broker
  - Celery Result Backend
  - Pub/Sub für WebSocket-Updates
  - Persistente Daten in Volume

**Sicherheit:**
- Passwortgeschützt (`requirepass`)
- Nur über lokales Interface erreichbar
- Datenpersistenz über Docker Volume

### 2. Application Layer (docker-compose.app.yml)

#### 2.1 FastAPI Web Server
- **Container:** `apify-web`
- **Base Image:** Python 3.9.6
- **Port:** `8000` (intern)
- **Command:** `uvicorn main:app --host 0.0.0.0 --port 8000`

**Hauptfunktionen:**
- **REST API Endpoints:**
  - `GET /` - HTML Landing Page
  - `GET /health` - Health Check
  - `POST /scrape/async` - TikTok Video Scraping starten
  - `GET /task/{task_id}` - Task-Status abfragen
  - `GET /tasks/active` - Aktive Tasks anzeigen

- **WebSocket Endpoint:**
  - `WebSocket /wss/{task_id}?token={jwt}` - Echtzeit Task-Updates

**Authentifizierung:**
- JWT-Token Validierung mit Supabase
- HS256 Algorithmus
- Audience: "authenticated"
- User ID aus Token extrahiert (`sub` Claim)

**Umgebungsvariablen:**
- `REDIS_URL`: Redis-Verbindungs-URL
- `OPENAI_API_KEY`: OpenAI API Schlüssel
- `APIFY_API_TOKEN`: Apify API Token
- `SUPABASE_JWT_SECRET`: JWT Secret für Token-Verifizierung
- `VIRTUAL_HOST`: Domain für Nginx-Proxy
- `LETSENCRYPT_HOST`: Domain für SSL-Zertifikat

#### 2.2 Celery Worker
- **Container:** `apify-worker`
- **Base Image:** Python 3.9.6
- **Command:** `celery -A tasks worker --loglevel=info --pool=gevent --concurrency=20`

**Hauptfunktionen:**
- Asynchrone Task-Verarbeitung
- Gevent-Pool für parallele I/O-Operationen
- Bis zu 20 gleichzeitige Tasks

**Task-Pipeline:**
1. **Initialisierung** - TikTok Scraper Setup
2. **Scraping** - Apify Actor ausführen
3. **Video-Verarbeitung** - Frames & Untertitel extrahieren
4. **AI-Verarbeitung** - OpenAI GPT-4 für Rezeptextraktion
5. **Finalisierung** - Upload zu Supabase

**Redis Pub/Sub Integration:**
- Veröffentlicht Progress-Updates
- WebSocket Manager hört auf `task_updates` Channel
- Echtzeit-Updates an verbundene Clients

#### 2.3 Redis Health Check
- **Container:** `redis-check`
- **Funktion:** Wartet bis Redis bereit ist vor App-Start
- **Command:** Ping-Loop bis Redis antwortet

### 3. Netzwerk-Architektur

#### 3.1 proxy-network
- **Driver:** bridge
- **Zweck:** Verbindung zwischen Nginx und Web-Services
- **Zugriff:** Nginx Proxy, FastAPI Web Server

#### 3.2 app-network
- **Driver:** bridge
- **Zweck:** Interne Service-Kommunikation
- **Zugriff:** Web Server, Worker, Redis

**Isolation:**
- Redis ist nur über `app-network` erreichbar
- Kein direkter Internet-Zugriff zu Redis
- Nginx ist einziger öffentlicher Einstiegspunkt

### 4. Data Flow & Processing Pipeline

#### 4.1 Request Flow
```
Client → HTTPS (443) → Nginx Proxy → FastAPI Web (8000)
         ↓
    JWT Validation
         ↓
    Create Celery Task
         ↓
    Return task_id
         ↓
    WebSocket Connection (/wss/{task_id})
```

#### 4.2 Task Processing Flow
```
Celery Worker receives task
         ↓
Step 1: Initialize TikTok Scraper
         ↓
Step 2: Run Apify Actor
         ↓  (Scrapes TikTok with proxies)
         ↓
Step 3: Download & Process Video
         ↓  (Extract frames, subtitles, text)
         ↓
Step 4: OpenAI GPT-4 Analysis
         ↓  (Extract recipe from content)
         ↓
Step 5: Upload to Supabase
         ↓
Return recipe_id & status
```

#### 4.3 WebSocket Update Flow
```
Celery Worker → publish_websocket_update()
         ↓
    Redis Pub/Sub ("task_updates")
         ↓
WebSocket Manager (listen_for_updates)
         ↓
Broadcast to connected WebSockets
         ↓
    Client receives real-time update
```

### 5. Externe Service-Integration

#### 5.1 Apify Integration
**Service:** `ApifyService` (services.py)
- **Actor ID:** `S5h7zRLfKFEr8pdj7`
- **Proxy:** Apify Residential Proxies
- **Features:**
  - Video Download
  - Subtitle Download
  - Anti-Blocking (max 5 retries, 120s timeout)

**Scraping-Konfiguration:**
```python
{
    "postURLs": [video_url],
    "scrapeRelatedVideos": False,
    "shouldDownloadVideos": True,
    "shouldDownloadSubtitles": True,
    "maxRequestRetries": 5,
    "requestTimeoutSecs": 120,
    "proxyConfiguration": {
        "useApifyProxy": True,
        "groups": ["RESIDENTIAL"]
    }
}
```

#### 5.2 OpenAI Integration
**Service:** `OpenAIService` (services.py)
- **Model:** GPT-4 Vision
- **Input:** Video Frames + Subtitles + Text
- **Output:** Strukturiertes Rezept (JSON)
- **Prompt:** Multi-Language Support (prompt_service.py)

#### 5.3 Supabase Integration
**Service:** `SupabaseService` (services.py)
- **Authentifizierung:** JWT Token Validation
- **Datenbank:** PostgreSQL (Recipe Storage)
- **Storage:** Media Files (optional)
- **Row Level Security:** User-basierte Datenisolierung

### 6. Deployment

#### 6.1 Initial Setup (VPS)
```bash
# 1. Infrastructure aufsetzen
./setup-infra.sh

# Erstellt:
# - Docker Networks (proxy-network, app-network)
# - Nginx Proxy Container
# - Let's Encrypt Companion
# - Redis Server
```

#### 6.2 Application Deployment
```bash
# 2. App deployen
./deploy-app.sh

# Ausführung:
# - Stoppt alte App-Container
# - Baut neue Images (--no-cache)
# - Startet Web + Worker Container
# - Health Check auf /health endpoint
# - Cleanup alter Docker Images
```

#### 6.3 DNS-Konfiguration
**Erforderlich:**
- A-Record: `resimply.app` → VPS IP-Adresse
- SSL-Zertifikat wird automatisch von Let's Encrypt erstellt
- Nginx übernimmt automatisches HTTP→HTTPS Redirect

### 7. Sicherheit

#### 7.1 Authentifizierung & Autorisierung
- **JWT Tokens:** Supabase HS256 Signatur
- **Token Validation:** Bei jedem API-Request
- **User Isolation:** Tasks sind user-spezifisch
- **WebSocket Auth:** Token als Query-Parameter

#### 7.2 Network Security
- **Redis:** Nur localhost Binding (127.0.0.1)
- **Redis Auth:** Passwortgeschützt
- **Internal Networks:** Docker bridge networks
- **SSL/TLS:** Automatisch von Let's Encrypt

#### 7.3 API Security
- **Rate Limiting:** (Implementierung optional)
- **CORS:** (Konfiguration in FastAPI)
- **Input Validation:** Pydantic Models
- **Error Handling:** Keine Secrets in Error Messages

### 8. Monitoring & Logging

#### 8.1 Health Checks
```bash
# System Health
GET /health

# Response:
{
  "status": "healthy",
  "redis_connected": true,
  "services": ["web", "redis", "worker"]
}
```

#### 8.2 Container Logs
```bash
# Web Server Logs
docker compose -f docker-compose.app.yml logs web -f

# Worker Logs
docker compose -f docker-compose.app.yml logs worker -f

# Redis Logs
docker compose -f docker-compose.infrastructure.yml logs redis -f

# Nginx Logs
docker compose -f docker-compose.infrastructure.yml logs nginx -f
```

#### 8.3 Task Monitoring
```bash
# Aktive Tasks
GET /tasks/active

# Task Status
GET /task/{task_id}

# WebSocket (Echtzeit)
WebSocket /wss/{task_id}?token={jwt}
```

### 9. Skalierung

#### 9.1 Horizontal Scaling
**Worker Scaling:**
```bash
# Mehr Worker starten
docker compose -f docker-compose.app.yml up -d --scale worker=3
```

**Web Server Scaling:**
```bash
# Load Balancing über Nginx
docker compose -f docker-compose.app.yml up -d --scale web=2
```

#### 9.2 Vertical Scaling
**Redis Memory:**
```yaml
redis:
  command: redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 2gb
```

**Celery Concurrency:**
```yaml
worker:
  command: celery -A tasks worker --loglevel=info --pool=gevent --concurrency=50
```

### 10. Backup & Recovery

#### 10.1 Datenpersistenz
**Docker Volumes:**
- `redis-data`: Redis Datenbank
- `nginx-certs`: SSL-Zertifikate
- `nginx-vhost`: Nginx Virtual Host Configs

**Backup-Strategie:**
```bash
# Redis Backup
docker exec redis-server redis-cli -a $REDIS_PASSWORD SAVE
docker cp redis-server:/data/dump.rdb ./backup/

# Volume Backup
docker run --rm -v redis-data:/data -v $(pwd):/backup ubuntu tar czf /backup/redis-backup.tar.gz /data
```

#### 10.2 Disaster Recovery
```bash
# Infrastructure neu aufsetzen
./setup-infra.sh

# Redis Daten wiederherstellen
docker cp ./backup/dump.rdb redis-server:/data/

# App deployen
./deploy-app.sh
```

### 11. Umgebungsvariablen (.env)

```bash
# Redis
REDIS_PASSWORD=super_secure_password_here

# Domain
MAIN_DOMAIN=resimply.app

# SSL
LETSENCRYPT_EMAIL=admin@resimply.app

# Supabase
SUPABASE_JWT_SECRET=your_jwt_secret_here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key_here

# API Keys
OPENAI_API_KEY=sk-your-openai-key
APIFY_API_TOKEN=apify_api_your-token

# Redis URL (automatisch generiert)
REDIS_URL=redis://:${REDIS_PASSWORD}@redis-server:6379/0
```

### 12. Performance-Optimierungen

#### 12.1 Apify Optimierungen
- Residential Proxies zur Blockierungsvermeidung
- Request Retries (5x) mit exponential backoff
- Concurrency=1 zur Rate-Limit-Vermeidung
- 120s Timeout für langsame Videos

#### 12.2 Redis Optimierungen
- In-Memory Datenbank für schnelle Queue-Operations
- Pub/Sub für Echtzeit-Updates ohne Polling
- Result Expiration (3600s) zur Memory-Freigabe

#### 12.3 Worker Optimierungen
- Gevent Pool für I/O-gebundene Operationen
- Concurrency=20 für parallele Video-Verarbeitung
- Async/Await für OpenAI API-Calls

#### 12.4 WebSocket Optimierungen
- Direkte Redis Pub/Sub Integration
- Keine Polling-Delays
- Connection Pooling
- 60-Minuten Timeout für lange Tasks

### 13. Troubleshooting

#### 13.1 Häufige Probleme

**Problem: SSL-Zertifikat wird nicht erstellt**
```bash
# DNS prüfen
dig resimply.app

# Let's Encrypt Logs
docker logs nginx-letsencrypt

# Lösung: DNS muss auf VPS-IP zeigen (A-Record)
```

**Problem: Redis Connection Failed**
```bash
# Redis Status prüfen
docker exec redis-server redis-cli -a $REDIS_PASSWORD ping

# Redis Logs
docker logs redis-server

# Lösung: redis-check Container prüfen
```

**Problem: Task bleibt in PENDING**
```bash
# Worker Status
docker logs apify-worker

# Celery Inspect
docker exec apify-worker celery -A tasks inspect active

# Lösung: Worker neu starten
docker compose -f docker-compose.app.yml restart worker
```

**Problem: WebSocket Connection Failed**
```bash
# Nginx Config prüfen
docker exec nginx-proxy cat /etc/nginx/vhost.d/resimply.app_location

# WebSocket Headers prüfen
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" https://resimply.app/wss/test

# Lösung: nginx-websocket.conf Volume prüfen
```

### 14. Wartung

#### 14.1 Updates
```bash
# App Update (via GitHub Actions oder manuell)
cd /path/to/app
git pull
./deploy-app.sh

# Infrastructure Update (selten nötig)
docker compose -f docker-compose.infrastructure.yml pull
docker compose -f docker-compose.infrastructure.yml up -d
```

#### 14.2 Cleanup
```bash
# Alte Docker Images entfernen
docker image prune -a -f

# Alte Container Logs löschen
docker container prune -f

# Redis Memory Monitoring
docker exec redis-server redis-cli -a $REDIS_PASSWORD INFO memory
```

#### 14.3 Monitoring
- Health Endpoint regelmäßig prüfen
- Redis Memory Usage überwachen
- SSL-Zertifikat Ablauf (automatisch erneuert)
- Disk Space auf VPS überwachen

---

## Zusammenfassung

Die Infrastruktur von **resimply.app** ist eine moderne, containerisierte Microservices-Architektur:

- **Frontend:** HTTPS mit automatischem SSL
- **Backend:** FastAPI mit JWT-Auth
- **Queue:** Celery + Redis für asynchrone Verarbeitung
- **Echtzeit:** WebSocket mit Redis Pub/Sub
- **Skalierbar:** Docker Compose für einfaches Scaling
- **Sicher:** Network Isolation, JWT Auth, SSL/TLS
- **Wartbar:** Separate Infrastructure & App Layer

**URL:** https://resimply.app
**Deployment:** Automatisiert via Shell-Scripts
**Monitoring:** Health Checks + Container Logs
**Backup:** Docker Volumes für Datenpersistenz
