#!/bin/bash
# Einmalige Infrastructure Setup auf dem VPS
echo "🚀 Setting up Infrastructure..."
# Environment laden
source .env_old
# Infrastructure Networks und Volumes erstellen
docker compose -f docker-compose.infrastructure.yml up -d
echo "⏳ Waiting for services to be ready..."
sleep 30
# Redis Connection testen
docker exec redis-server redis-cli -a $REDIS_PASSWORD ping
# Nginx Status prüfen
curl -I http://localhost
echo "✅ Infrastructure is running!"
echo "🔒 SSL certificates will be automatically created when your app starts"
echo ""
echo "Next steps:"
echo "1. Make sure your DNS points to this server"
echo "2. Update your .env with correct domain names"
echo "3. Deploy your app with: ./deploy-app.sh"