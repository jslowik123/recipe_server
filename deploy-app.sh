#!/bin/bash
# App Deployment Script - wird von GitHub Actions aufgerufen

echo "🚀 Deploying Application..."

# Environment laden
source .env

# App Container stoppen (Infrastructure läuft weiter!)
docker compose -f docker-compose.app.yml down

# Code ist bereits durch GitHub Actions aktualisiert

# App Container bauen und starten
echo "🔨 Building app containers..."
docker compose -f docker-compose.app.yml build --no-cache

echo "🚀 Starting app containers..."
docker compose -f docker-compose.app.yml up -d

# Health Check
echo "⏳ Waiting for app to be ready..."
sleep 15

# Health Check
if curl -f http://localhost/health > /dev/null 2>&1; then
    echo "✅ App deployed successfully!"
    
    # Cleanup alte Images
    docker image prune -f
    
    echo "📊 Container Status:"
    docker compose -f docker-compose.app.yml ps
else
    echo "❌ Health check failed!"
    echo "📋 App logs:"
    docker compose -f docker-compose.app.yml logs web
    exit 1
fi