# TikTok Recipe Extractor

A FastAPI-based system that extracts recipes from TikTok videos using Apify scraping and OpenAI vision processing.

## 🚀 Quick Start

1. **Setup Environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure API Keys:**
   Create `.env` file:
   ```
   APIFY_API_TOKEN=your_apify_token_here
   OPENAI_API_KEY=your_openai_key_here
   REDIS_URL=redis://localhost:6379
   ```

3. **Start Services:**
   ```bash
   # Start Redis (required)
   docker run -d -p 6379:6379 redis:alpine
   
   # Start the API
   python main.py
   
   # Start Celery worker (in another terminal)
   celery -A tasks worker --loglevel=info
   ```

## 📋 Core Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI web server and API endpoints |
| `tasks.py` | Celery tasks for async processing |
| `tracking.py` | Cost and usage tracking system |

## 🧪 Testing & Debugging

| Tool | Purpose | Usage |
|------|---------|-------|
| `url_tester.py` | Test if TikTok URLs work | `python url_tester.py 'URL'` |
| `enhanced_recipe_test.py` | Full extraction test | `python enhanced_recipe_test.py 'URL'` |
| `view_costs.py` | View tracking data | `python view_costs.py` |

## 🔧 API Endpoints

- `POST /scrape/async` - Start async extraction
- `GET /task/{task_id}` - Check task status
- `GET /health` - Health check
- `GET /debug/env` - Environment check

## 📊 Tracking

All extractions are tracked in `recipe_extraction_tracking.xlsx` with:
- Token usage and costs
- Processing times
- Success/failure rates
- Full recipe data

## 🐳 Docker

```bash
docker-compose up -d
```

## 📝 Example Usage

```python
import requests

# Start extraction
response = requests.post('http://localhost:8000/scrape/async', 
    json={'url': 'https://www.tiktok.com/@user/video/ID'})
task_id = response.json()['task_id']

# Check status
status = requests.get(f'http://localhost:8000/task/{task_id}')
print(status.json())
```

## ⚠️ Important Notes

- Only public TikTok videos work
- Videos may become inaccessible over time
- Test URLs with `url_tester.py` first
- Check logs for debugging issues

## 🔍 Troubleshooting

1. **"Post not found or private"** → Video is private/deleted, try different URL
2. **No text/subtitles extracted** → Video has no captions, extraction limited
3. **OpenAI errors** → Check API key and rate limits
4. **Redis connection issues** → Ensure Redis is running

## 📈 Costs

Typical costs per extraction:
- GPT-4o: ~$0.02-0.05 per video
- GPT-4o-mini: ~$0.002-0.005 per video

Check `view_costs.py` for detailed tracking.