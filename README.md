# Recipify API

A scalable FastAPI-based microservice that automatically extracts recipes from TikTok videos using AI vision and NLP. Built with modern async/await patterns, real-time WebSocket updates, and distributed task processing.

## 🎯 Key Features

- **AI-Powered Recipe Extraction**: Analyzes video frames using GPT-4 Vision to extract ingredients, steps, and metadata
- **Asynchronous Processing**: Celery-based distributed task queue for handling multiple scraping jobs concurrently
- **Real-time Updates**: WebSocket support for live progress tracking during recipe extraction
- **Cloud Storage Integration**: Automatic upload to Supabase Storage with Row-Level Security (RLS)
- **Production-Ready**: Docker Compose setup with Redis, health checks, and proper logging

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   FastAPI   │────▶│   Celery     │────▶│   Apify     │
│   Server    │     │   Workers    │     │   Scraper   │
└──────┬──────┘     └──────┬───────┘     └─────────────┘
       │                   │
       │              ┌────▼─────┐
       │              │  Redis   │
       │              │ Pub/Sub  │
       │              └──────────┘
       │
   ┌───▼────────┐    ┌──────────────┐
   │ WebSocket  │    │   Supabase   │
   │  Manager   │    │   Storage    │
   └────────────┘    └──────────────┘
```

## 🚀 Tech Stack

- **Backend**: FastAPI, Python 3.11+
- **Task Queue**: Celery with Redis broker
- **AI/ML**: OpenAI GPT-4 Vision, OpenCV for video processing
- **Storage**: Supabase (PostgreSQL + S3-compatible storage)
- **Web Scraping**: Apify TikTok Scraper
- **Infrastructure**: Docker, Docker Compose, Nginx

## 📦 Project Structure

```
apify/
├── src/                      # Source code
│   ├── config.py            # Configuration management
│   ├── services.py          # Service layer (Apify, OpenAI, Supabase)
│   ├── tasks.py             # Celery task definitions
│   ├── tiktok_scraper.py    # Main scraping orchestrator
│   ├── websocket_manager.py # WebSocket connection manager
│   ├── prompt_service.py    # AI prompt templates
│   ├── detailed_logger.py   # Structured logging
│   └── exceptions.py        # Custom exceptions
├── tests/                   # Unit and integration tests
├── scripts/                 # Deployment scripts
├── main.py                  # FastAPI application entry point
├── docker-compose.*.yml     # Docker orchestration
└── requirements.txt         # Python dependencies
```

## 🔧 Installation

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- OpenAI API key
- Apify API token
- Supabase project

### Local Development

1. Clone the repository:
```bash
git clone <repository-url>
cd apify
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys
```

5. Start infrastructure services:
```bash
docker-compose -f docker-compose.infrastructure.yml up -d
```

6. Run the application:
```bash
python main.py
```

### Docker Deployment

```bash
# Start all services
docker-compose -f docker-compose.infrastructure.yml up -d
docker-compose -f docker-compose.app.yml up -d
```

## 📡 API Endpoints

### POST `/scrape/async`
Start asynchronous recipe extraction from TikTok video.

**Request:**
```json
{
  "url": "https://www.tiktok.com/@user/video/123",
  "language": "de"
}
```

**Response:**
```json
{
  "task_id": "abc-123-def",
  "status": "PENDING",
  "message": "Started scraping TikTok video"
}
```

### GET `/task/{task_id}`
Check task status and retrieve results.

### WebSocket `/wss/{task_id}?token={jwt}`
Real-time updates for task progress.

### GET `/health`
Health check endpoint for monitoring.

## 🔐 Authentication

Uses Supabase JWT tokens for authentication. Include JWT token in:
- HTTP: `Authorization: Bearer <token>`
- WebSocket: Query parameter `?token=<jwt_token>`

## 🧪 Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_supabase_upload.py

# Run with coverage
pytest --cov=src tests/
```

## 📊 Monitoring & Logging

- Structured JSON logging for all operations
- Redis-based task progress tracking
- Health check endpoints for container orchestration
- Celery Flower dashboard (optional)

## 🔄 Workflow

1. User submits TikTok URL via API
2. Celery worker downloads video via Apify
3. Video frames extracted using OpenCV
4. GPT-4 Vision analyzes frames for recipe content
5. Structured recipe data created
6. Thumbnail generated and uploaded to Supabase
7. Recipe metadata stored in PostgreSQL
8. Real-time progress sent via WebSocket

## 🚧 Known Limitations

- Requires valid TikTok video URLs
- Processing time depends on video length (typically 30-60s)
- Rate limited by OpenAI API quotas

## 🤝 Contributing

This is a portfolio project. Feel free to fork and adapt for your own use.

## 📝 License

MIT License - See LICENSE file for details

## 👤 Author

Jasper Slowik
- Email: jasper.slowik@icloud.com
- GitHub: [Your GitHub Profile]

## 🙏 Acknowledgments

- OpenAI for GPT-4 Vision API
- Apify for TikTok scraping infrastructure
- Supabase for backend services
