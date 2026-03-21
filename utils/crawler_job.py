"""
Crawler Job (Indexer) - Multi-threaded web crawler.

Features:
- Runs in a separate thread
- Configurable: origin, max_depth, hit_rate, max_queue_capacity, max_urls_to_visit
- Rate limiting (requests per second)
- Back-pressure (URL queue capacity limit)
- Pause/Resume/Stop controls
- Persists state for resume after interruption
"""

import threading
import time
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from collections import deque
from enum import Enum

from utils.storage import (
    generate_crawler_id,
    create_crawler_directory,
    save_crawler_status,
    load_crawler_status,
    append_crawler_log,
    save_crawler_queue,
    load_crawler_queue,
    is_url_visited,
    mark_url_visited,
    add_word_entries_batch
)
from utils.html_parser import parse_html, count_word_frequencies


class CrawlerState(Enum):
    """Crawler state machine."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


class CrawlerJob:
    """
    Multi-threaded web crawler that indexes pages.

    Configuration:
        origin: Starting URL
        max_depth: Maximum crawl depth (0 = origin only)
        hit_rate: Requests per second (rate limiting)
        max_queue_capacity: Maximum URLs in queue (back-pressure)
        max_urls_to_visit: Maximum total URLs to visit
    """

    USER_AGENT = "PythonCrawler/1.0 (Educational Project)"
    TIMEOUT = 10  # HTTP request timeout in seconds

    def __init__(self, origin: str, max_depth: int = 2, hit_rate: float = 1.0,
                 max_queue_capacity: int = 1000, max_urls_to_visit: int = 100,
                 crawler_id: str = None):
        """Initialize crawler with configuration."""
        # Configuration
        self.origin = origin
        self.max_depth = max_depth
        self.hit_rate = hit_rate
        self.max_queue_capacity = max_queue_capacity
        self.max_urls_to_visit = max_urls_to_visit

        # Generate or use provided crawler ID
        self.crawler_id = crawler_id or generate_crawler_id()

        # State
        self.state = CrawlerState.IDLE
        self._state_lock = threading.Lock()

        # Control events
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially
        self._stop_event = threading.Event()

        # Queue: (url, depth)
        self._queue = deque()
        self._queue_lock = threading.Lock()

        # Statistics
        self.stats = {
            'urls_visited': 0,
            'urls_indexed': 0,
            'words_indexed': 0,
            'errors': 0,
            'start_time': None,
            'end_time': None
        }

        # Thread reference
        self._thread = None

        # Rate limiting
        self._last_request_time = 0

    def _log(self, message: str):
        """Append log entry."""
        append_crawler_log(self.crawler_id, message)

    def _save_state(self):
        """Persist current state to disk."""
        status = {
            'crawler_id': self.crawler_id,
            'origin': self.origin,
            'max_depth': self.max_depth,
            'hit_rate': self.hit_rate,
            'max_queue_capacity': self.max_queue_capacity,
            'max_urls_to_visit': self.max_urls_to_visit,
            'state': self.state.value,
            'stats': self.stats
        }
        save_crawler_status(self.crawler_id, status)

        # Save queue
        with self._queue_lock:
            queue_list = [f"{url}|{depth}" for url, depth in self._queue]
        save_crawler_queue(self.crawler_id, queue_list)

    def _load_state(self):
        """Load state from disk (for resume)."""
        status = load_crawler_status(self.crawler_id)
        if status:
            self.stats = status.get('stats', self.stats)

        queue_list = load_crawler_queue(self.crawler_id)
        with self._queue_lock:
            self._queue.clear()
            for item in queue_list:
                if '|' in item:
                    url, depth = item.rsplit('|', 1)
                    self._queue.append((url, int(depth)))

    def _rate_limit(self):
        """Enforce rate limiting based on hit_rate."""
        if self.hit_rate <= 0:
            return

        min_interval = 1.0 / self.hit_rate
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def _fetch_url(self, url: str) -> str:
        """Fetch URL content using urllib. Returns HTML or None."""
        try:
            request = Request(
                url,
                headers={'User-Agent': self.USER_AGENT}
            )
            with urlopen(request, timeout=self.TIMEOUT) as response:
                # Only accept status 200
                if response.status != 200:
                    return None

                # Only process HTML content
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' not in content_type.lower():
                    return None

                # Read and decode content
                charset = response.headers.get_content_charset() or 'utf-8'
                return response.read().decode(charset, errors='ignore')

        except (URLError, HTTPError) as e:
            self._log(f"Error fetching {url}: {e}")
            self.stats['errors'] += 1
            return None
        except Exception as e:
            self._log(f"Unexpected error fetching {url}: {e}")
            self.stats['errors'] += 1
            return None

    def _add_to_queue(self, url: str, depth: int):
        """Add URL to queue with back-pressure check."""
        with self._queue_lock:
            # Back-pressure: reject if queue is full
            if len(self._queue) >= self.max_queue_capacity:
                return False

            # Don't add if already visited
            if is_url_visited(url):
                return False

            self._queue.append((url, depth))
            return True

    def _process_page(self, url: str, depth: int):
        """Process a single page: fetch, parse, index."""
        # Rate limit
        self._rate_limit()

        # Fetch page
        html_content = self._fetch_url(url)
        if html_content is None:
            return

        # Mark as visited
        mark_url_visited(url)
        self.stats['urls_visited'] += 1

        # Parse HTML
        result = parse_html(html_content, url)
        title = result['title'] or url
        links = result['links']
        words = result['words']

        self._log(f"Indexed: {title[:50]} ({len(words)} words, {len(links)} links)")

        # Count word frequencies
        word_freq = count_word_frequencies(words)

        # Index words to storage
        entries = [
            (word, url, self.origin, depth, freq)
            for word, freq in word_freq.items()
        ]
        if entries:
            count = add_word_entries_batch(entries)
            self.stats['words_indexed'] += count
            self.stats['urls_indexed'] += 1

        # Add discovered links to queue (if not at max depth)
        if depth < self.max_depth:
            for link in links:
                if not is_url_visited(link):
                    self._add_to_queue(link, depth + 1)

    def _crawl_loop(self):
        """Main crawling loop (runs in thread)."""
        self.stats['start_time'] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._log(f"Starting crawl from {self.origin}")

        # Initialize queue with origin URL (force add, skip visited check)
        with self._queue_lock:
            self._queue.append((self.origin, 0))

        while True:
            # Check for stop signal
            if self._stop_event.is_set():
                with self._state_lock:
                    self.state = CrawlerState.STOPPED
                self._log("Crawler stopped by user")
                break

            # Check for pause signal
            if not self._pause_event.is_set():
                self._save_state()
                self._pause_event.wait()  # Block until resumed
                if self._stop_event.is_set():
                    continue

            # Check if we've reached max URLs
            if self.stats['urls_visited'] >= self.max_urls_to_visit:
                with self._state_lock:
                    self.state = CrawlerState.COMPLETED
                self._log(f"Completed: reached max URLs ({self.max_urls_to_visit})")
                break

            # Get next URL from queue
            with self._queue_lock:
                if not self._queue:
                    with self._state_lock:
                        self.state = CrawlerState.COMPLETED
                    self._log("Completed: queue empty")
                    break
                url, depth = self._queue.popleft()

            # Skip if already visited
            if is_url_visited(url):
                continue

            # Process the page
            try:
                self._process_page(url, depth)
            except Exception as e:
                self._log(f"Error processing {url}: {e}")
                self.stats['errors'] += 1

            # Save state periodically (every 10 URLs)
            if self.stats['urls_visited'] % 10 == 0:
                self._save_state()

        # Final state save
        self.stats['end_time'] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save_state()
        self._log(f"Crawl finished. Stats: {self.stats}")

    def start(self):
        """Start the crawler in a new thread."""
        with self._state_lock:
            if self.state not in (CrawlerState.IDLE, CrawlerState.STOPPED, CrawlerState.COMPLETED):
                raise RuntimeError(f"Cannot start crawler in state: {self.state}")

            self.state = CrawlerState.RUNNING

        # Create crawler directory
        create_crawler_directory(self.crawler_id)
        self._save_state()

        # Reset control events
        self._pause_event.set()
        self._stop_event.clear()

        # Start thread
        self._thread = threading.Thread(target=self._crawl_loop, daemon=True)
        self._thread.start()

        self._log(f"Crawler started with ID: {self.crawler_id}")
        return self.crawler_id

    def pause(self):
        """Pause the crawler."""
        with self._state_lock:
            if self.state != CrawlerState.RUNNING:
                return False
            # Set state immediately so UI sees the change
            self.state = CrawlerState.PAUSED
        self._pause_event.clear()
        self._log("Crawler pausing...")
        return True

    def resume(self):
        """Resume a paused crawler."""
        with self._state_lock:
            if self.state != CrawlerState.PAUSED:
                return False
            # Set state immediately so UI sees the change
            self.state = CrawlerState.RUNNING
        self._pause_event.set()
        self._log("Crawler resuming...")
        return True

    def stop(self):
        """Stop the crawler."""
        with self._state_lock:
            if self.state not in (CrawlerState.RUNNING, CrawlerState.PAUSED):
                return False
            # Set state immediately so UI sees the change
            self.state = CrawlerState.STOPPED
        self._stop_event.set()
        self._pause_event.set()  # Unblock if paused
        self._log("Crawler stopping...")
        return True

    def get_status(self) -> dict:
        """Get current crawler status."""
        with self._queue_lock:
            queue_size = len(self._queue)

        return {
            'crawler_id': self.crawler_id,
            'state': self.state.value,
            'origin': self.origin,
            'config': {
                'max_depth': self.max_depth,
                'hit_rate': self.hit_rate,
                'max_queue_capacity': self.max_queue_capacity,
                'max_urls_to_visit': self.max_urls_to_visit
            },
            'stats': self.stats,
            'queue_size': queue_size
        }

    def is_alive(self) -> bool:
        """Check if crawler thread is still running."""
        return self._thread is not None and self._thread.is_alive()


# Registry to track active crawlers
_active_crawlers = {}
_registry_lock = threading.Lock()


def create_crawler(origin: str, max_depth: int = 2, hit_rate: float = 1.0,
                   max_queue_capacity: int = 1000, max_urls_to_visit: int = 100) -> CrawlerJob:
    """Create and register a new crawler."""
    crawler = CrawlerJob(
        origin=origin,
        max_depth=max_depth,
        hit_rate=hit_rate,
        max_queue_capacity=max_queue_capacity,
        max_urls_to_visit=max_urls_to_visit
    )

    with _registry_lock:
        _active_crawlers[crawler.crawler_id] = crawler

    return crawler


def get_crawler(crawler_id: str) -> CrawlerJob:
    """Get a crawler by ID."""
    with _registry_lock:
        return _active_crawlers.get(crawler_id)


def list_crawlers() -> list:
    """List all registered crawlers."""
    with _registry_lock:
        return [c.get_status() for c in _active_crawlers.values()]
