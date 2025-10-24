# Wardroberry API

AI-Powered Wardrobe Management System with Docker, HTTPS, Legal Routing, and JWT Authentication.

## Features

✅ **AI Clothing Analysis** - OpenAI Vision API für automatische Kleidungserkennung
✅ **Wardrobe Management** - Kleiderschrank-Verwaltung mit Kategorien, Farben, Styles
✅ **Outfit Planning** - Outfit-Kombinationen erstellen und verwalten
✅ **Docker Setup** - Production-ready mit Nginx Reverse Proxy
✅ **HTTPS/SSL** - Automatische Let's Encrypt Zertifikate
✅ **JWT Authentication** - Supabase Token Verification
✅ **Rate Limiting** - IP + User-ID basiert
✅ **Legal Routes** - Privacy Policy, Terms, Imprint (DE/EN)
✅ **Support Page** - Mehrsprachige Support-Seite
✅ **Async Processing** - Redis Queue für Background-Jobs

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ HTTPS
┌──────▼──────────────────┐
│  Nginx Proxy            │  ← Let's Encrypt SSL
│  + Let's Encrypt        │
└──────┬──────────────────┘
       │
┌──────▼──────────────────┐
│  FastAPI Web Server     │  ← main.py
│  - Wardroberry Routes   │
│  - Legal Routes         │
│  - Health Checks        │
└──────┬──────────────────┘
       │
       ├────────────┬────────────┬────────────┐
       │            │            │            │
┌──────▼─────┐ ┌───▼────┐ ┌─────▼─────┐ ┌───▼────┐
│ Supabase   │ │ Redis  │ │  OpenAI   │ │ Worker │
│ DB+Storage │ │ Queue  │ │  Vision   │ │ (AI)   │
└────────────┘ └────────┘ └───────────┘ └────────┘
```

## Project Structure

```
.
├── main.py                          # FastAPI Application
├── src/
│   ├── routes/
│   │   ├── legal.py                 # Legal documents (Privacy, Terms, Imprint)
│   │   └── wardroberry.py           # Wardrobe API routes
│   ├── helper/
│   │   ├── verify_token.py          # JWT Token verification
│   │   ├── rate_limit.py            # Rate limiting
│   │   └── exceptions.py            # Custom exceptions
│   ├── ai.py                        # OpenAI Vision wrapper
│   ├── database_manager.py          # Supabase database layer
│   ├── storage_manager.py           # Supabase storage layer
│   ├── queue_manager.py             # Redis queue management
│   ├── worker.py                    # Background job processor
│   └── config.py                    # Configuration management
├── legal/
│   ├── de/                          # German legal documents
│   └── en/                          # English legal documents
├── docker-compose.app.yml           # Application services
├── docker-compose.infrastructure.yml # Infrastructure (Nginx, Redis)
├── Dockerfile
├── requirements.txt
└── .env.example

```

## API Endpoints

### Core Routes
- `GET /` - Index page
- `GET /health` - Health check (Redis, Supabase, OpenAI)
- `GET /support?lang=de|en` - Support page

### Legal Routes (DE/EN)
- `GET /legal/privacy?lang=de&format=html|json` - Privacy Policy
- `GET /legal/terms?lang=de&format=html|json` - Terms of Service
- `GET /legal/imprint?lang=de&format=html|json` - Imprint

### Wardrobe API (requires JWT Bearer token)
- `POST /api/wardrobe/upload` - Upload clothing image
- `GET /api/wardrobe/clothes` - Get user's clothing items
- `GET /api/wardrobe/clothes/{id}` - Get specific clothing item
- `DELETE /api/wardrobe/clothes/{id}` - Delete clothing item
- `POST /api/wardrobe/outfits` - Create outfit
- `GET /api/wardrobe/outfits` - Get user's outfits
- `GET /api/wardrobe/outfits/{id}` - Get specific outfit
- `DELETE /api/wardrobe/outfits/{id}` - Delete outfit
- `GET /api/wardrobe/stats` - Get user statistics
- `GET /api/wardrobe/queue/stats` - Get processing queue stats

## Setup

### 1. Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env_old.example .env_old
```

Required variables:
```env
# Redis
REDIS_PASSWORD=your_secure_password

# OpenAI
OPENAI_API_KEY=sk-your-key-here

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_JWT_SECRET=your-jwt-secret

# Domain (for production)
MAIN_DOMAIN=your-domain.com
LETSENCRYPT_EMAIL=your-email@example.com
```

### 2. Supabase Database Setup

Run the database schema from `src/database_structure.txt` in your Supabase SQL editor.

Required tables:
- `users` - User profiles
- `clothes` - Clothing items
- `outfits` - Outfit combinations
- `outfit_items` - Junction table

Required storage buckets:
- `clothing-images-original`
- `clothing-images-processed`

### 3. Start Infrastructure (Redis + Nginx)

```bash
docker-compose -f docker-compose.infrastructure.yml up -d
```

This starts:
- Nginx Proxy (Port 80, 443)
- Let's Encrypt Companion
- Redis Server

### 4. Start Application

```bash
docker-compose -f docker-compose.app.yml up -d
```

This starts:
- FastAPI Web Server (exposed via Nginx)
- Wardroberry Worker (background processing)

### 5. Check Health

```bash
curl https://your-domain.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "services": {
    "redis": true,
    "database": true,
    "storage": true,
    "openai": true
  }
}
```

## Development

### Local Development (without Docker)

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export REDIS_HOST=localhost
export REDIS_PORT=6379
export REDIS_DB=0
export OPENAI_API_KEY=sk-...
export SUPABASE_URL=https://...
export SUPABASE_ANON_KEY=...
export SUPABASE_JWT_SECRET=...
```

3. Start Redis locally:
```bash
redis-server
```

4. Start FastAPI:
```bash
uvicorn main:app --reload
```

5. Start Worker (in separate terminal):
```bash
python -m src.worker
```

### API Documentation

FastAPI generates automatic interactive docs:
- Swagger UI: `https://your-domain.com/docs`
- ReDoc: `https://your-domain.com/redoc`

## Authentication

All `/api/wardrobe/*` endpoints require a Bearer token from Supabase:

```bash
curl -H "Authorization: Bearer YOUR_SUPABASE_JWT" \
  https://your-domain.com/api/wardrobe/clothes
```

The token is verified using `SUPABASE_JWT_SECRET` and extracts the user ID for authorization.

## Rate Limiting

Rate limiting is enabled on sensitive endpoints:
- 1 request/minute for `/rate_limit_test`
- Tracks by user ID (if authenticated) or IP address
- IP addresses are anonymized for GDPR compliance

## Monitoring

### Docker Logs

```bash
# Web server logs
docker logs wardroberry-web -f

# Worker logs
docker logs wardroberry-worker -f

# Nginx logs
docker logs nginx-proxy -f
```

### Health Checks

```bash
# Overall health
curl https://your-domain.com/health

# Queue stats (requires auth)
curl -H "Authorization: Bearer TOKEN" \
  https://your-domain.com/api/wardrobe/queue/stats
```

## Migration Notes

This project was migrated from a TikTok scraping service. The following features were preserved:

**Kept from TikTok Project:**
- Docker infrastructure (Nginx Proxy + Let's Encrypt)
- Legal routing system
- Support page with language switching
- JWT token verification
- Rate limiting with IP anonymization
- Redis integration
- Health check system

**Replaced:**
- ❌ Celery → ✅ Custom Redis Queue + Worker
- ❌ Apify TikTok Scraper → ✅ OpenAI Clothing Analysis
- ❌ Video processing → ✅ Image processing
- ❌ Recipe extraction → ✅ Wardrobe management

## License

Private project - All rights reserved.
