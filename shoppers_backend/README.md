# Shoppers E-Commerce API

A production-ready Django REST Framework API for e-commerce product scraping and AI-powered avatar generation. This project integrates Nordstrom product scraping via Apify, asynchronous task processing with Celery, and OpenAI's DALL-E 3 for personalized avatar generation.

## 🚀 Features

- **Product Scraping**: Automated Nordstrom product scraping using Apify actors
- **Robust Error Handling**: Retry mechanisms, rate limiting, and comprehensive error recovery
- **Knowledge Bases**: Separate databases for filters/info and products for fast retrieval
- **Batch Processing**: Efficient batch database operations for optimal performance
- **Async Task Processing**: Celery-based background task execution with Redis
- **AI Avatar Generation**: Generate Pixar-style avatars from photos using OpenAI DALL-E 3 and LangChain
- **RESTful API**: Clean, documented API endpoints for all operations
- **Task Scheduling**: Automated daily scraping via Celery Beat
- **Task Status Tracking**: Real-time task status monitoring
- **Connection Pooling**: Reusable HTTP connections for faster scraping

## 📋 Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Endpoints](#api-endpoints)
- [Development](#development)
- [Production Deployment](#production-deployment)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)

## 🔧 Prerequisites

- **Python**: 3.8 or higher
- **Redis**: 5.0 or higher (for Celery message broker)
- **API Keys**:
  - Apify API Token (for web scraping)
  - OpenAI API Key (for avatar generation)

## 📦 Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd shoppers_ecommerce
```

### 2. Create Virtual Environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables

Create a `.env` file in the project root:

```bash
# Django Configuration
SECRET_KEY=your-secret-key-here
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,localhost,127.0.0.1

# Database (Production - PostgreSQL recommended)
DATABASE_URL=postgresql://user:password@localhost:5432/shoppers_db

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# API Keys
APIFY_API_TOKEN=your-apify-api-token
APIFY_ACTOR_ID=trudax/actor-nordstrom-scraper
OPENAI_API_KEY=your-openai-api-key
```

**⚠️ Important**: Never commit the `.env` file to version control. It's already included in `.gitignore`.

## ⚙️ Configuration

### Database Setup

For production, it's recommended to use PostgreSQL instead of SQLite:

```bash
# Install PostgreSQL adapter
pip install psycopg2-binary
```

Update `settings.py` to use PostgreSQL:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}
```

### Redis Setup

Install and start Redis:

**Windows:**
```bash
# Using Docker
docker run -d -p 6379:6379 redis

# Or download from https://github.com/microsoftarchive/redis/releases
```

**Linux:**
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis
```

**Mac:**
```bash
brew install redis
brew services start redis
```

## 🏃 Running the Application

### Development Mode

#### 1. Start Redis

```bash
# Windows (Docker)
docker run -d -p 6379:6379 redis

# Linux/Mac
redis-server
```

#### 2. Run Database Migrations

```bash
python manage.py migrate
```

#### 3. Create Superuser (Optional)

```bash
python manage.py createsuperuser
```

#### 4. Start Django Development Server

```bash
python manage.py runserver
```

#### 5. Start Celery Worker (in a separate terminal)

```bash
# Windows
celery -A shoppers_ecommerce worker --loglevel=info --pool=solo

# Linux/Mac
celery -A shoppers_ecommerce worker --loglevel=info
```

#### 6. Start Celery Beat (optional, for scheduled tasks)

```bash
celery -A shoppers_ecommerce beat --loglevel=info
```

The API will be available at `http://localhost:8000`

## 📡 API Endpoints

### Base URL
```
http://localhost:8000/api/
```

### 1. Trigger Scraping Task
**Endpoint**: `GET /api/trigger-scraping/`

Trigger the Nordstrom product scraping task. Prevents multiple instances from running simultaneously.

**Response** (Success):
```json
{
  "status": "success",
  "message": "Scraping task started",
  "task_id": "abc123-def456-ghi789"
}
```

**Response** (Task Already Running):
```json
{
  "status": "error",
  "message": "Scraping task is already running. Please wait for it to complete.",
  "running_task_id": "xyz789-abc123-def456"
}
```

### 2. Check Task Status
**Endpoint**: `GET /api/task-status/?task_id=<task_id>`

Check the status of a running or completed task.

**Query Parameters**:
- `task_id` (required): The task ID returned from the trigger endpoint

**Response** (Pending):
```json
{
  "task_id": "abc123-def456-ghi789",
  "state": "PENDING",
  "ready": false,
  "status": "pending"
}
```

**Response** (Success):
```json
{
  "task_id": "abc123-def456-ghi789",
  "state": "SUCCESS",
  "ready": true,
  "status": "success",
  "result": {...}
}
```

**Response** (Error):
```json
{
  "task_id": "abc123-def456-ghi789",
  "state": "FAILURE",
  "ready": true,
  "status": "error",
  "error": "Error message here"
}
```

### 3. Generate Avatar
**Endpoint**: `POST /api/generate-avatar/`

Generate a Pixar-style 3D avatar from an uploaded photo using OpenAI DALL-E 3.

**Request**:
- Method: `POST`
- Content-Type: `multipart/form-data`
- Body: `photo` (file) - JPEG, PNG, or WebP image

**Response** (Success):
```json
{
  "status": "success",
  "image_url": "https://...",
  "image_base64": "base64-encoded-image-data",
  "used_prompt": "A full-body 3D render of a SINGLE cute Pixar-style character..."
}
```

**Response** (Error):
```json
{
  "status": "error",
  "message": "Photo file is required."
}
```

**Example using curl**:
```bash
curl -X POST http://localhost:8000/api/generate-avatar/ \
  -F "photo=@/path/to/photo.jpg"
```

**Example using Python**:
```python
import requests

url = "http://localhost:8000/api/generate-avatar/"
files = {"photo": open("photo.jpg", "rb")}
response = requests.post(url, files=files)
print(response.json())
```

### 4. Extract Filters & Info (Knowledge Base)
**Endpoint**: `POST /api/extract-filters/`

Extract filters and information from Nordstrom dashboard (categories, brands, sizes, colors, etc.) and save to the knowledge base. This API builds a comprehensive filter database for faster retrieval.

**Request Body** (Optional):
```json
{
  "base_url": "https://www.nordstrom.com/",
  "async": true
}
```

**Response** (Success - Async):
```json
{
  "status": "success",
  "message": "Filter extraction task started",
  "task_id": "abc123-def456-ghi789",
  "mode": "async"
}
```

**Response** (Success - Sync):
```json
{
  "status": "success",
  "message": "Filters extracted successfully",
  "result": {
    "status": "success",
    "filters_extracted": 125,
    "filters": ["category: Women", "brand: Nike", ...],
    "total_in_db": 125
  },
  "mode": "sync"
}
```

**GET Request - Retrieve Filters**:
**Endpoint**: `GET /api/extract-filters/`

Query the filters knowledge base with optional filters.

**Query Parameters**:
- `filter_type` (optional): Filter by type (e.g., 'category', 'brand', 'size', 'color')
- `search` (optional): Search filter names
- `limit` (optional): Number of results (default: 100)
- `offset` (optional): Pagination offset (default: 0)

**Example**:
```bash
# Get all categories
curl "http://localhost:8000/api/extract-filters/?filter_type=category"

# Search for specific brand
curl "http://localhost:8000/api/extract-filters/?filter_type=brand&search=Nike"
```

### 5. Scrape Products (Knowledge Base)
**Endpoint**: `POST /api/scrape-products/`

Scrape Nordstrom products and save them to the products knowledge base for faster retrieval and search.

**Request Body** (Optional):
```json
{
  "search_terms": ["Jeans", "Tops", "Shirts", "Shoes"],
  "max_items_per_term": 50,
  "async": true
}
```

**Response** (Success - Async):
```json
{
  "status": "success",
  "message": "Product scraping task started",
  "task_id": "xyz789-abc123-def456",
  "mode": "async"
}
```

**Response** (Success - Sync):
```json
{
  "status": "success",
  "message": "Products scraped successfully",
  "result": {
    "status": "success",
    "products_saved": 150,
    "products_updated": 20,
    "total_products": 170,
    "errors": []
  },
  "mode": "sync"
}
```

**GET Request - Retrieve Products**:
**Endpoint**: `GET /api/scrape-products/`

Query the products knowledge base with advanced filters.

**Query Parameters**:
- `brand` (optional): Filter by brand name
- `category` (optional): Filter by category
- `min_price` (optional): Minimum price filter
- `max_price` (optional): Maximum price filter
- `in_stock` (optional): Filter by stock status (true/false)
- `search` (optional): Search product titles
- `limit` (optional): Number of results (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Example**:
```bash
# Get all products from Nike
curl "http://localhost:8000/api/scrape-products/?brand=Nike"

# Search for jeans under $100
curl "http://localhost:8000/api/scrape-products/?category=Jeans&max_price=100"

# Search products by keyword
curl "http://localhost:8000/api/scrape-products/?search=running&in_stock=true"
```

**Example using Python**:
```python
import requests

# Extract filters
url = "http://localhost:8000/api/extract-filters/"
response = requests.post(url, json={"async": True})
task_id = response.json()["task_id"]

# Check status
status_url = f"http://localhost:8000/api/task-status/?task_id={task_id}"
status = requests.get(status_url)
print(status.json())

# Scrape products
products_url = "http://localhost:8000/api/scrape-products/"
response = requests.post(products_url, json={
    "search_terms": ["Jeans", "Shoes"],
    "max_items_per_term": 30,
    "async": True
})
task_id = response.json()["task_id"]

# Query products
query_url = "http://localhost:8000/api/scrape-products/"
products = requests.get(query_url, params={
    "brand": "Nike",
    "min_price": 50,
    "max_price": 150,
    "in_stock": True
})
print(products.json())
```

## 💻 Development

### Project Structure

```
shoppers_ecommerce/
├── api/                    # Main API application
│   ├── views.py           # API view endpoints
│   ├── tasks.py           # Celery tasks
│   ├── models.py          # Database models
│   ├── urls.py            # URL routing
│   └── static/            # Static files
├── shoppers_ecommerce/    # Project settings
│   ├── settings.py        # Django settings
│   ├── celery.py          # Celery configuration
│   └── urls.py            # Root URL configuration
├── manage.py              # Django management script
├── requirements.txt       # Python dependencies
└── .env                   # Environment variables (not in git)
```

### Running Tests

```bash
python manage.py test
```

### Code Quality

Before committing, ensure your code follows PEP 8:

```bash
pip install flake8 black
flake8 .
black .
```

## 🚢 Production Deployment

### Security Checklist

1. **Set `DEBUG=False`** in production settings
2. **Use a strong `SECRET_KEY`** (generate a new one, never use the default)
3. **Set proper `ALLOWED_HOSTS`** with your domain
4. **Use HTTPS** with SSL certificates
5. **Use a production database** (PostgreSQL recommended)
6. **Set up proper logging** and monitoring
7. **Configure static files** serving (whitenoise or CDN)
8. **Set up proper CORS** settings if using frontend
9. **Use environment variables** for all sensitive data
10. **Enable security middleware** (already included)

### Production Settings Example

Create `settings_production.py`:

```python
from .settings import *
import os

DEBUG = False
SECRET_KEY = os.getenv('SECRET_KEY')
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# Static files
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Security settings
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'django.log'),
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
```

### Deployment with Gunicorn

```bash
pip install gunicorn
gunicorn shoppers_ecommerce.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

### Celery in Production

Run Celery worker as a systemd service:

```ini
# /etc/systemd/system/celery-worker.service
[Unit]
Description=Celery Worker
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/path/to/shoppers_ecommerce
EnvironmentFile=/path/to/.env
ExecStart=/path/to/venv/bin/celery -A shoppers_ecommerce worker --loglevel=info

[Install]
WantedBy=multi-user.target
```

### Using Docker (Optional)

Example `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "shoppers_ecommerce.wsgi:application", "--bind", "0.0.0.0:8000"]
```

## 🐛 Troubleshooting

### Celery Worker Issues

**Issue**: PermissionError on Windows
**Solution**: The configuration automatically uses the 'solo' pool on Windows. If issues persist, run:
```bash
celery -A shoppers_ecommerce worker --loglevel=info --pool=solo
```

### Redis Connection Issues

**Issue**: Connection refused to Redis
**Solution**: 
- Verify Redis is running: `redis-cli ping` (should return "PONG")
- Check Redis URL in `.env` file
- Ensure Redis is accessible on the configured port

### Missing Environment Variables

**Issue**: API errors about missing tokens
**Solution**: Ensure all required environment variables are set in your `.env` file:
- `APIFY_API_TOKEN`
- `OPENAI_API_KEY`
- `SECRET_KEY`

### Database Migration Issues

**Issue**: Database errors
**Solution**: 
```bash
python manage.py makemigrations
python manage.py migrate
```

## 🔒 Security Notes

1. **Never commit sensitive data** - The `.env` file is gitignored for a reason
2. **Rotate keys regularly** - Change API keys periodically
3. **Use strong passwords** - For database and admin access
4. **Monitor logs** - Set up logging and alerting in production
5. **Rate limiting** - Consider adding rate limiting for API endpoints
6. **API authentication** - Consider adding API key authentication for production

## 📝 License

[Add your license here]

## 👥 Contributors

[Add contributors here]

## 📞 Support

For issues and questions, please open an issue on the repository.

## 🔄 Version History

- **v1.0.0** - Initial release with product scraping and avatar generation

---

**Made with ❤️ using Django, Celery, and OpenAI**

