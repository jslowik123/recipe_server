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

# Health Check mit Retry-Logik
echo "⏳ Waiting for app to be ready..."
MAX_RETRIES=10
RETRY_DELAY=5
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo "🔍 Health check attempt $((RETRY_COUNT + 1))/$MAX_RETRIES..."

    if curl -f https://${MAIN_DOMAIN}/health > /dev/null 2>&1; then
        echo "✅ App deployed successfully!"

        # Cleanup alte Images
        docker image prune -f

        echo "📊 Container Status:"
        docker compose -f docker-compose.app.yml ps
        exit 0
    fi

    RETRY_COUNT=$((RETRY_COUNT + 1))

    if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
        echo "⏳ App not ready yet, waiting ${RETRY_DELAY}s before retry..."
        sleep $RETRY_DELAY
    fi
done

echo "❌ Health check failed after $MAX_RETRIES attempts!"
echo "📋 App logs:"
docker compose -f docker-compose.app.yml logs web
echo ""
echo "ℹ️  Note: If the app is actually running, this might be a temporary network/SSL issue."
echo "    Check manually: curl https://${MAIN_DOMAIN}/health"
exit 1