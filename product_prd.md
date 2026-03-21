# Product Requirements Document (PRD): Web Crawler & Search Engine

## 1. Project Overview
The objective is to build a functional web crawler and real-time search engine from scratch using Python. The system must consist of an active multi-threaded Indexer, a concurrent Searcher, and a web-based UI. 

**CRITICAL CONSTRAINT:** Use Python's native standard libraries (`urllib`, `html.parser`, `threading`) for the core crawling and parsing logic. Do not use `requests`, `BeautifulSoup`, or `Scrapy`. You may use `Flask` strictly for exposing the backend API.

## 2. System Architecture & Tech Stack
* **Backend:** Python 3 + Flask (API Server running on port 3600).
* **Frontend:** Vanilla HTML, CSS, and JS (stored in a `demo/` folder).
* **Concurrency:** Python `threading` for running asynchronous crawler jobs.
* **Storage:** File-system based (NoSQL approach) stored in a `data/` directory.

### 2.1. File-Based Storage Structure
The system must persist state to the filesystem to allow resuming after interruptions:
* `data/visited_urls.data`: Global list of visited URLs to prevent infinite loops.
* `data/crawlers/[crawler_id].json/log/data`: Stores the specific crawler's status, logs, and queue (implementing back-pressure). Crawler ID format: `[EpochTimeCreated]_[ThreadID]`.
* `data/storage/[letter].data`: Words discovered by the crawler are indexed by their first letter (e.g., `a.data`). Each line contains: `word, relevant_url, origin_url, depth, frequency`.

### 2.2. The Indexer (Crawler Job)
* Receives configuration: `origin`, `max_depth`, `hit_rate` (requests per second), `max_queue_capacity` (for back-pressure), and `max_urls_to_visit`.
* Runs in a separate thread.
* Checks `visited_urls.data` before fetching. Uses native `urllib` to fetch HTML (status 200).
* Extracts words and links using native `html.parser`.
* Writes discovered words and frequencies to the `data/storage/` files.
* Must support Pause, Resume, and Stop operations via the API.

### 2.3. The Search Engine
* Executes queries against the `data/storage/` filesystem.
* Matches the query string to the initial letter files, sorts results by frequency, and returns paginated triples: `(relevant_url, origin_url, depth)`.
* Must run concurrently without locking the active crawler threads.

### 2.4. Web Interface (Frontend)
Create three distinct pages in the `demo/` folder:
1.  **Crawler (`crawler.html`):** Form to initiate a new crawler job with all parameters.
2.  **Crawler Status (`status.html`):** Real-time dashboard using long-polling to display active logs, indexing progress, and queue depth.
3.  **Search (`search.html`):** A search bar returning paginated results with the relevant URL, origin, and depth.

## 3. Implementation Phases
**Phase 1: Project Setup & Core Utils**
* Create `utils/html_parser.py` and `utils/crawler_job.py`. Set up the `data/` folder structure logic.

**Phase 2: Services & API (Flask)**
* Create `services/crawler_service.py` and `services/search_service.py`.
* Create `app.py` to expose endpoints (e.g., `/crawler/create`, `/crawler/status/<id>`, `/search`).

**Phase 3: Frontend Construction**
* Build the UI files in the `demo/` folder and connect them to the Flask API. Ensure real-time UI updates for the status page.