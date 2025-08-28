# Docker-Basiertes Deployment Setup

## Einmalige VPS-Einrichtung

### 1. Repository klonen
```bash
git clone <dein-repo>
cd apify
```

### 2. Environment konfigurieren
```bash
cp .env.example .env
nano .env  # Domains und Passwörter anpassen
```

### 3. Scripts ausführbar machen
```bash
chmod +x setup-infrastructure.sh
chmod +x deploy-app.sh
```

### 4. Infrastructure starten (einmalig)
```bash
./setup-infrastructure.sh
```

### 5. App deployen
```bash
./deploy-app.sh
```

## Was passiert:

### Infrastructure Container (laufen permanent):
- **nginx-proxy**: Automatischer Reverse Proxy
- **nginx-letsencrypt**: Automatische SSL-Zertifikate  
- **redis-server**: Task Queue (persistent data)

### App Container (werden bei Deployment erneuert):
- **apify-web**: FastAPI App
- **apify-worker**: Celery Worker
- **apify-flower**: Monitoring

## Deployment Workflow:

1. **Code push zu main branch**
2. **GitHub Actions startet**
3. **Nur App-Container werden erneuert** (Infrastructure läuft weiter)
4. **SSL und Redis bleiben unberührt**
5. **~15 Sekunden Deployment-Zeit**

## SSL:
- Automatische Erstellung beim ersten App-Start
- Automatische Erneuerung alle 60 Tage
- Läuft komplett im nginx-letsencrypt Container

## Monitoring:
- Main App: https://deine-domain.com
- Flower: https://flower.deine-domain.com  
- Health Check: https://deine-domain.com/health

## Wichtige Commands:

```bash
# Infrastructure Status
docker compose -f docker-compose.infrastructure.yml ps

# App Status  
docker compose -f docker-compose.app.yml ps

# Logs anschauen
docker compose -f docker-compose.app.yml logs -f web

# Infrastructure neu starten (nur bei Problemen)
docker compose -f docker-compose.infrastructure.yml restart

# Komplettes Reset (Vorsicht!)
docker compose -f docker-compose.app.yml down
docker compose -f docker-compose.infrastructure.yml down
```