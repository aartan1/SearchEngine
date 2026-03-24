"""
File-Based Storage System for Web Crawler & Search Engine

Storage Structure:
    data/
    ├── visited_urls.data           # Global URL deduplication
    ├── crawlers/
    │   └── [epoch]_[threadid]/
    │       ├── crawler.json        # Status & config
    │       ├── crawler.log         # Activity logs
    │       └── crawler.data        # URL queue
    └── storage/
        ├── a.data ... z.data       # Words by first letter
        └── numbers.data            # Words starting with digits
"""

import os
import json
import threading
import time
from pathlib import Path


# Base directories
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
CRAWLERS_DIR = DATA_DIR / "crawlers"
STORAGE_DIR = DATA_DIR / "storage"
VISITED_URLS_FILE = DATA_DIR / "visited_urls.data"


# Per-letter file locks (27 total: a-z + numbers)
_file_locks = {letter: threading.Lock() for letter in 'abcdefghijklmnopqrstuvwxyz'}
_file_locks['numbers'] = threading.Lock()

# Lock for visited_urls.data
_visited_urls_lock = threading.Lock()

# Lock for crawler log files
_crawler_log_lock = threading.Lock()

# In-memory cache for visited URLs (dramatically improves hit rate)
_visited_urls_cache = None
_visited_urls_cache_lock = threading.Lock()


def _ensure_visited_cache():
    """Load visited URLs into memory cache if not already loaded."""
    global _visited_urls_cache
    if _visited_urls_cache is None:
        with _visited_urls_cache_lock:
            if _visited_urls_cache is None:
                _visited_urls_cache = load_visited_urls_from_disk()


def load_visited_urls_from_disk() -> set:
    """Load all visited URLs from disk into a set."""
    with _visited_urls_lock:
        if not VISITED_URLS_FILE.exists():
            return set()
        with open(VISITED_URLS_FILE, 'r', encoding='utf-8') as f:
            return set(line.strip() for line in f if line.strip())


def init_storage():
    """Initialize the storage directory structure."""
    DATA_DIR.mkdir(exist_ok=True)
    CRAWLERS_DIR.mkdir(exist_ok=True)
    STORAGE_DIR.mkdir(exist_ok=True)

    # Create empty visited_urls.data if not exists
    if not VISITED_URLS_FILE.exists():
        VISITED_URLS_FILE.touch()

    # Create letter files (a-z) and numbers.data
    for letter in 'abcdefghijklmnopqrstuvwxyz':
        letter_file = STORAGE_DIR / f"{letter}.data"
        if not letter_file.exists():
            letter_file.touch()

    numbers_file = STORAGE_DIR / "numbers.data"
    if not numbers_file.exists():
        numbers_file.touch()


# =============================================================================
# Visited URLs Management
# =============================================================================

def load_visited_urls() -> set:
    """Load all visited URLs into a set for O(1) lookup."""
    global _visited_urls_cache
    _ensure_visited_cache()
    with _visited_urls_cache_lock:
        return _visited_urls_cache.copy()


def clear_visited_urls() -> int:
    """Clear all visited URLs. Returns count of cleared URLs."""
    global _visited_urls_cache
    with _visited_urls_cache_lock:
        with _visited_urls_lock:
            if not VISITED_URLS_FILE.exists():
                return 0
            with open(VISITED_URLS_FILE, 'r', encoding='utf-8') as f:
                count = sum(1 for line in f if line.strip())
            with open(VISITED_URLS_FILE, 'w', encoding='utf-8') as f:
                f.write('')
            _visited_urls_cache = set()
            return count


def clear_visited_urls_by_domain(domain: str) -> int:
    """Clear visited URLs matching a domain. Returns count of cleared URLs."""
    global _visited_urls_cache
    with _visited_urls_cache_lock:
        with _visited_urls_lock:
            if not VISITED_URLS_FILE.exists():
                return 0
            with open(VISITED_URLS_FILE, 'r', encoding='utf-8') as f:
                urls = [line.strip() for line in f if line.strip()]

            # Filter out URLs matching the domain
            kept = [url for url in urls if domain not in url]
            cleared = len(urls) - len(kept)

            with open(VISITED_URLS_FILE, 'w', encoding='utf-8') as f:
                for url in kept:
                    f.write(url + '\n')

            # Update cache
            if _visited_urls_cache is not None:
                _visited_urls_cache = set(kept)

            return cleared


def is_url_visited(url: str) -> bool:
    """Check if URL has already been visited. Uses in-memory cache for O(1) lookup."""
    global _visited_urls_cache
    _ensure_visited_cache()
    with _visited_urls_cache_lock:
        return url in _visited_urls_cache


def mark_url_visited(url: str) -> None:
    """Mark a URL as visited. Updates both cache and disk."""
    global _visited_urls_cache
    _ensure_visited_cache()
    with _visited_urls_cache_lock:
        _visited_urls_cache.add(url)
    with _visited_urls_lock:
        with open(VISITED_URLS_FILE, 'a', encoding='utf-8') as f:
            f.write(url + '\n')


# =============================================================================
# Word Index Storage (a-z + numbers.data)
# =============================================================================

def _get_storage_file(word: str) -> tuple:
    """
    Determine which storage file a word belongs to.
    Returns (file_path, lock_key) or (None, None) if word should be ignored.
    """
    if not word:
        return None, None

    first_char = word[0].lower()

    if first_char.isalpha():
        return STORAGE_DIR / f"{first_char}.data", first_char
    elif first_char.isdigit():
        return STORAGE_DIR / "numbers.data", 'numbers'
    else:
        # Ignore symbols, unicode, emojis
        return None, None


def add_word_entry(word: str, relevant_url: str, origin_url: str, depth: int, frequency: int) -> bool:
    """
    Add a word entry to the appropriate storage file.

    Format: word, relevant_url, origin_url, depth, frequency

    Returns True if added, False if ignored (symbol/unicode).
    """
    file_path, lock_key = _get_storage_file(word)

    if file_path is None:
        return False

    entry = f"{word}, {relevant_url}, {origin_url}, {depth}, {frequency}\n"

    with _file_locks[lock_key]:
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(entry)

    return True


def add_word_entries_batch(entries: list) -> int:
    """
    Add multiple word entries efficiently.

    Each entry is a tuple: (word, relevant_url, origin_url, depth, frequency)

    Groups entries by first letter to minimize lock acquisitions.
    Returns count of entries added.
    """
    # Group entries by their target file
    grouped = {}
    for word, relevant_url, origin_url, depth, frequency in entries:
        file_path, lock_key = _get_storage_file(word)
        if file_path is None:
            continue
        if lock_key not in grouped:
            grouped[lock_key] = []
        grouped[lock_key].append(f"{word}, {relevant_url}, {origin_url}, {depth}, {frequency}\n")

    # Write each group with a single lock acquisition
    count = 0
    for lock_key, lines in grouped.items():
        file_path = STORAGE_DIR / (f"{lock_key}.data" if lock_key != 'numbers' else "numbers.data")
        with _file_locks[lock_key]:
            with open(file_path, 'a', encoding='utf-8') as f:
                f.writelines(lines)
        count += len(lines)

    return count


def search_word(word: str) -> list:
    """
    Search for a word in the storage files.

    Returns list of tuples: (relevant_url, origin_url, depth, frequency)
    sorted by frequency descending.
    """
    file_path, lock_key = _get_storage_file(word)

    if file_path is None or not file_path.exists():
        return []

    results = []
    word_lower = word.lower()

    with _file_locks[lock_key]:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 5 and parts[0].lower() == word_lower:
                    results.append({
                        'relevant_url': parts[1],
                        'origin_url': parts[2],
                        'depth': int(parts[3]),
                        'frequency': int(parts[4])
                    })

    # Sort by frequency descending
    results.sort(key=lambda x: x['frequency'], reverse=True)
    return results


# =============================================================================
# Crawler Files Management
# =============================================================================

def generate_crawler_id() -> str:
    """Generate unique crawler ID: [EpochTime]_[ThreadID]"""
    epoch = int(time.time())
    thread_id = threading.current_thread().ident
    return f"{epoch}_{thread_id}"


def create_crawler_directory(crawler_id: str) -> Path:
    """Create directory for a new crawler and initialize files."""
    crawler_dir = CRAWLERS_DIR / crawler_id
    crawler_dir.mkdir(exist_ok=True)

    # Initialize empty files
    (crawler_dir / "crawler.json").touch()
    (crawler_dir / "crawler.log").touch()
    (crawler_dir / "crawler.data").touch()

    return crawler_dir


def save_crawler_status(crawler_id: str, status: dict) -> None:
    """Save crawler status/config to JSON file."""
    json_file = CRAWLERS_DIR / crawler_id / "crawler.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(status, f, indent=2)


def load_crawler_status(crawler_id: str) -> dict:
    """Load crawler status/config from JSON file."""
    json_file = CRAWLERS_DIR / crawler_id / "crawler.json"
    if not json_file.exists():
        return {}
    with open(json_file, 'r', encoding='utf-8') as f:
        content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)


def append_crawler_log(crawler_id: str, message: str) -> None:
    """Append a log entry to crawler's log file. Thread-safe."""
    log_file = CRAWLERS_DIR / crawler_id / "crawler.log"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        # Ensure directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with _crawler_log_lock:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {message}\n")
                f.flush()
    except Exception as e:
        print(f"[LOG ERROR] Failed to write log: {e}")


def read_crawler_log(crawler_id: str) -> list:
    """Read all log entries from crawler's log file. Thread-safe."""
    log_file = CRAWLERS_DIR / crawler_id / "crawler.log"
    if not log_file.exists():
        return []
    with _crawler_log_lock:
        with open(log_file, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]


def save_crawler_queue(crawler_id: str, queue: list) -> None:
    """Save URL queue to crawler's data file."""
    data_file = CRAWLERS_DIR / crawler_id / "crawler.data"
    with open(data_file, 'w', encoding='utf-8') as f:
        for url in queue:
            f.write(url + '\n')


def load_crawler_queue(crawler_id: str) -> list:
    """Load URL queue from crawler's data file."""
    data_file = CRAWLERS_DIR / crawler_id / "crawler.data"
    if not data_file.exists():
        return []
    with open(data_file, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


def list_all_crawlers() -> list:
    """List all crawler IDs in the crawlers directory."""
    if not CRAWLERS_DIR.exists():
        return []
    return [d.name for d in CRAWLERS_DIR.iterdir() if d.is_dir()]


# Initialize storage on module import
init_storage()
