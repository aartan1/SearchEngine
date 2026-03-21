"""
Search Service - Concurrent search engine against file-based index.

Features:
- Query execution against data/storage/ files
- Multi-word query support
- Frequency-based ranking
- Pagination support
- Concurrent execution (doesn't lock crawler threads)
"""

import threading
from pathlib import Path
from collections import defaultdict

# Storage paths
BASE_DIR = Path(__file__).parent.parent
STORAGE_DIR = BASE_DIR / "data" / "storage"

# Read locks (separate from write locks in storage.py)
# This allows concurrent reads while crawlers write
_read_locks = {letter: threading.Lock() for letter in 'abcdefghijklmnopqrstuvwxyz'}
_read_locks['numbers'] = threading.Lock()


def _get_storage_file(word: str) -> tuple:
    """
    Determine which storage file a word belongs to.
    Returns (file_path, lock_key) or (None, None) if invalid.
    """
    if not word:
        return None, None

    first_char = word[0].lower()

    if first_char.isalpha():
        return STORAGE_DIR / f"{first_char}.data", first_char
    elif first_char.isdigit():
        return STORAGE_DIR / "numbers.data", 'numbers'
    else:
        return None, None


def _search_single_word(word: str) -> list:
    """
    Search for a single word in the index.

    Returns list of dicts: {relevant_url, origin_url, depth, frequency}
    """
    file_path, lock_key = _get_storage_file(word)

    if file_path is None or not file_path.exists():
        return []

    results = []
    word_lower = word.lower()

    with _read_locks[lock_key]:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 5 and parts[0].lower() == word_lower:
                    results.append({
                        'word': parts[0],
                        'relevant_url': parts[1],
                        'origin_url': parts[2],
                        'depth': int(parts[3]),
                        'frequency': int(parts[4])
                    })

    return results


def search(query: str, page: int = 1, page_size: int = 10) -> dict:
    """
    Execute a search query against the index.

    Supports multi-word queries. Results are ranked by total frequency
    across all matched words.

    Args:
        query: Search query string (one or more words)
        page: Page number (1-indexed)
        page_size: Results per page

    Returns:
        dict with keys:
            - results: List of (relevant_url, origin_url, depth) triples
            - total: Total number of results
            - page: Current page
            - page_size: Results per page
            - total_pages: Total number of pages
    """
    # Tokenize query
    words = _tokenize_query(query)

    if not words:
        return _empty_response(page, page_size)

    # Search for each word
    all_matches = []
    for word in words:
        matches = _search_single_word(word)
        all_matches.extend(matches)

    if not all_matches:
        return _empty_response(page, page_size)

    # Aggregate by URL - sum frequencies for same URL
    url_scores = defaultdict(lambda: {'frequency': 0, 'depth': float('inf'), 'origin_url': None})

    for match in all_matches:
        url = match['relevant_url']
        url_scores[url]['frequency'] += match['frequency']
        url_scores[url]['depth'] = min(url_scores[url]['depth'], match['depth'])
        url_scores[url]['origin_url'] = match['origin_url']

    # Convert to list and sort by frequency (descending)
    ranked_results = [
        {
            'relevant_url': url,
            'origin_url': data['origin_url'],
            'depth': data['depth'],
            'score': data['frequency']
        }
        for url, data in url_scores.items()
    ]
    ranked_results.sort(key=lambda x: x['score'], reverse=True)

    # Paginate
    total = len(ranked_results)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_results = ranked_results[start_idx:end_idx]

    # Format as triples (relevant_url, origin_url, depth)
    triples = [
        (r['relevant_url'], r['origin_url'], r['depth'])
        for r in page_results
    ]

    return {
        'results': triples,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages
    }


def search_with_details(query: str, page: int = 1, page_size: int = 10) -> dict:
    """
    Execute search with detailed results including scores.

    Returns full result objects instead of just triples.
    """
    words = _tokenize_query(query)

    if not words:
        return _empty_response(page, page_size)

    all_matches = []
    for word in words:
        matches = _search_single_word(word)
        all_matches.extend(matches)

    if not all_matches:
        return _empty_response(page, page_size)

    # Aggregate by URL
    url_scores = defaultdict(lambda: {'frequency': 0, 'depth': float('inf'), 'origin_url': None, 'matched_words': set()})

    for match in all_matches:
        url = match['relevant_url']
        url_scores[url]['frequency'] += match['frequency']
        url_scores[url]['depth'] = min(url_scores[url]['depth'], match['depth'])
        url_scores[url]['origin_url'] = match['origin_url']
        url_scores[url]['matched_words'].add(match['word'])

    # Convert to list and sort
    ranked_results = [
        {
            'relevant_url': url,
            'origin_url': data['origin_url'],
            'depth': data['depth'],
            'score': data['frequency'],
            'matched_words': list(data['matched_words'])
        }
        for url, data in url_scores.items()
    ]
    ranked_results.sort(key=lambda x: x['score'], reverse=True)

    # Paginate
    total = len(ranked_results)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    return {
        'results': ranked_results[start_idx:end_idx],
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'query_words': words
    }


def _tokenize_query(query: str) -> list:
    """
    Tokenize a query string into searchable words.

    - Converts to lowercase
    - Splits on non-alphanumeric characters
    - Filters words with length > 1
    """
    import re
    tokens = re.split(r'[^a-zA-Z0-9]+', query.lower())
    return [word for word in tokens if len(word) > 1]


def _empty_response(page: int, page_size: int) -> dict:
    """Return empty search response."""
    return {
        'results': [],
        'total': 0,
        'page': page,
        'page_size': page_size,
        'total_pages': 1
    }


def get_index_stats() -> dict:
    """
    Get statistics about the search index.

    Returns word counts per letter file.
    """
    stats = {}
    total_entries = 0

    for letter in 'abcdefghijklmnopqrstuvwxyz':
        file_path = STORAGE_DIR / f"{letter}.data"
        if file_path.exists():
            with _read_locks[letter]:
                with open(file_path, 'r', encoding='utf-8') as f:
                    count = sum(1 for _ in f)
            stats[letter] = count
            total_entries += count

    # Numbers file
    numbers_file = STORAGE_DIR / "numbers.data"
    if numbers_file.exists():
        with _read_locks['numbers']:
            with open(numbers_file, 'r', encoding='utf-8') as f:
                count = sum(1 for _ in f)
        stats['numbers'] = count
        total_entries += count

    return {
        'per_file': stats,
        'total_entries': total_entries
    }
