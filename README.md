# Web Crawler & Search Engine

A web crawler and search engine project developed from scratch in Python with file-based storage.

## Features

- **Multi-threaded Crawler**: Concurrent web scraper with 20 parallel workers
- **High Throughput**: Up to 50 requests/second (configurable up to 100)
- **Rate Limiting**: Configurable request rate limiting
- **Back-Pressure**: Memory management with queue capacity control
- **Duplicate Detection**: Prevents duplicate URLs in queue using hash set
- **Pause/Resume/Stop**: Full crawler control and management
- **Resume After Stop**: Stopped crawlers can be resumed from saved state
- **Resume After Interruption**: Crawlers persist state for recovery after server restart
- **Frequency-Based Ranking**: Search results ranked by word frequency
- **Pagination**: Pagination support for search results
- **Real-time Status**: Live crawler status with log streaming
- **In-Memory URL Cache**: Fast O(1) visited URL lookups with disk persistence

## Technologies

- **Backend**: Python 3 + Flask (Port 3600)
- **Frontend**: Vanilla HTML, CSS, JavaScript
- **Crawler**: Python `urllib` and `html.parser` (no external libraries)
- **Concurrency**: Python `threading` with ThreadPoolExecutor
- **Storage**: File system-based (NoSQL)

## Project Structure

```
SearchEngine/
├── app.py                    # Flask API server
├── services/
│   ├── crawler_service.py    # Crawler API layer
│   └── search_service.py     # Search service
├── utils/
│   ├── crawler_job.py        # Multi-threaded crawler
│   ├── html_parser.py        # HTML parsing
│   └── storage.py            # File storage operations
├── demo/
│   ├── crawler.html          # Crawler creation page
│   ├── status.html           # Status dashboard
│   └── search.html           # Search page
└── data/
    ├── visited_urls.data     # Visited URLs
    ├── crawlers/             # Crawler states and logs
    └── storage/              # Word indexes (a.data, b.data, ...)
```

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd SearchEngine

# Install Flask (single dependency)
pip install flask

# Start the server
python app.py
```

## Usage

Once the server starts, navigate to `http://localhost:3600`.

### Web Interface

| Page | URL | Description |
|------|-----|-------------|
| Search | `/` | Search engine homepage |
| Crawler | `/crawler` | Create new crawler |
| Status | `/status` | Crawler status dashboard |

### API Endpoints

#### Crawler Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/crawler/create` | Create and start a new crawler |
| GET | `/crawler/list` | List all crawlers |
| GET | `/crawler/status/<id>` | Get crawler status |
| GET | `/crawler/logs/<id>` | Get crawler logs |
| POST | `/crawler/pause/<id>` | Pause crawler |
| POST | `/crawler/resume/<id>` | Resume paused or stopped crawler |
| POST | `/crawler/stop/<id>` | Stop crawler |
| POST | `/crawler/clear-visited` | Clear visited URLs |
| GET | `/crawler/resumable` | List crawlers that can be resumed |

#### Search Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/search?q=<query>` | Perform search |
| GET | `/stats` | Get index statistics |

### Crawler Parameters

```json
{
  "origin": "https://example.com",
  "max_depth": 3,
  "hit_rate": 50.0,
  "max_queue_capacity": 2000,
  "max_urls_to_visit": 1000
}
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `origin` | - | Starting URL (required) |
| `max_depth` | 2 | Maximum crawl depth |
| `hit_rate` | 50.0 | Requests per second (0 = unlimited, max 100) |
| `max_queue_capacity` | 1000 | Maximum URLs in queue |
| `max_urls_to_visit` | 100 | Maximum total URLs to visit |

> **Note**: Worker count is fixed at 20 for optimal performance.

### Search Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `q` | - | Search query |
| `page` | 1 | Page number |
| `page_size` | 10 | Results per page |
| `detailed` | false | Detailed results (include scores) |

## Example Usage

### Create Crawler with cURL

```bash
# Fast crawl with high throughput
curl -X POST http://localhost:3600/crawler/create \
  -H "Content-Type: application/json" \
  -d '{
    "origin": "https://books.toscrape.com",
    "max_depth": 3,
    "hit_rate": 50,
    "max_queue_capacity": 2000,
    "max_urls_to_visit": 1500
  }'
```

### Resume a Stopped Crawler

```bash
curl -X POST http://localhost:3600/crawler/resume/<crawler_id>
```

### Search with cURL

```bash
curl "http://localhost:3600/search?q=python&page=1&page_size=10"
```

## Crawler States

| State | Description | Can Resume? |
|-------|-------------|-------------|
| `idle` | Not started | No |
| `running` | Currently crawling | No (already running) |
| `paused` | Temporarily paused | Yes |
| `stopped` | Manually stopped | Yes |
| `completed` | Finished crawling | No |
| `error` | Error occurred | No |

## Storage Structure

- **visited_urls.data**: All visited URLs (prevents revisiting)
- **crawlers/[id]/crawler.json**: Crawler configuration and state
- **crawlers/[id]/crawler.log**: Crawler logs
- **crawlers/[id]/crawler.data**: Saved queue for resume
- **storage/[letter].data**: Word index (one file per letter)
  - Format: `word, relevant_url, origin_url, depth, frequency`

## License

This project was developed for educational purposes.

## Production Deployment

See [RECOMMENDATIONS.md](RECOMMENDATIONS.md) for detailed recommendations on deploying this crawler into a production environment.
