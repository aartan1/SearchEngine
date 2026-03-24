"""
Crawler Service - API layer for crawler operations.

Provides a clean interface for the Flask API to interact with crawlers.
"""

from utils.crawler_job import (
    CrawlerJob,
    CrawlerState,
    create_crawler,
    get_crawler,
    list_crawlers,
    resume_crawler_from_disk,
    list_resumable_crawlers,
    clear_inactive_crawlers,
    clear_all_crawlers
)
from utils.storage import (
    read_crawler_log,
    load_crawler_status,
    list_all_crawlers
)


def create_new_crawler(origin: str, max_depth: int = 2, hit_rate: float = 50.0,
                       max_queue_capacity: int = 1000, max_urls_to_visit: int = 100) -> dict:
    """
    Create and start a new crawler job.

    Returns crawler status dict.
    """
    # Validate parameters
    if not origin:
        raise ValueError("Origin URL is required")
    if not origin.startswith(('http://', 'https://')):
        origin = 'https://' + origin

    # Create crawler
    crawler = create_crawler(
        origin=origin,
        max_depth=max_depth,
        hit_rate=hit_rate,
        max_queue_capacity=max_queue_capacity,
        max_urls_to_visit=max_urls_to_visit
    )

    # Start crawler
    crawler.start()

    return crawler.get_status()


def get_crawler_status(crawler_id: str) -> dict:
    """
    Get status of a specific crawler.

    Returns status dict or None if not found.
    """
    # Try active crawlers first
    crawler = get_crawler(crawler_id)
    if crawler:
        return crawler.get_status()

    # Try loading from disk
    status = load_crawler_status(crawler_id)
    if status:
        return status

    return None


def get_crawler_logs(crawler_id: str, last_n: int = 50) -> list:
    """
    Get recent logs for a crawler.

    Returns list of log entries.
    """
    logs = read_crawler_log(crawler_id)
    if last_n and last_n > 0:
        return logs[-last_n:]
    return logs


def pause_crawler(crawler_id: str) -> bool:
    """Pause a running crawler."""
    crawler = get_crawler(crawler_id)
    if crawler:
        return crawler.pause()
    return False


def resume_crawler(crawler_id: str) -> dict:
    """
    Resume a crawler (paused or stopped).

    - If paused: resumes in-memory crawler
    - If stopped/interrupted: loads from disk and restarts

    Returns dict with success status and message.
    """
    # Try active crawler first (for paused state)
    crawler = get_crawler(crawler_id)
    if crawler:
        if crawler.state == CrawlerState.PAUSED:
            success = crawler.resume()
            return {'success': success, 'message': 'Crawler resumed' if success else 'Could not resume'}
        elif crawler.state == CrawlerState.RUNNING:
            return {'success': False, 'message': 'Crawler is already running'}
        elif crawler.state in (CrawlerState.COMPLETED, CrawlerState.ERROR):
            return {'success': False, 'message': f'Crawler is {crawler.state.value}, cannot resume'}
        # For STOPPED or IDLE, fall through to disk resume

    # Load from disk and restart (for stopped/interrupted crawlers)
    resumed = resume_interrupted_crawler(crawler_id)
    if resumed:
        return {'success': True, 'message': 'Crawler resumed from saved state', 'status': resumed}

    return {'success': False, 'message': 'Crawler not found or cannot be resumed'}


def stop_crawler(crawler_id: str) -> bool:
    """Stop a crawler."""
    crawler = get_crawler(crawler_id)
    if crawler:
        return crawler.stop()
    return False


def get_all_crawlers() -> list:
    """
    Get list of all crawlers (active and historical).
    """
    results = []

    # Get active crawlers
    active = list_crawlers()
    active_ids = {c['crawler_id'] for c in active}
    results.extend(active)

    # Get historical crawlers from disk
    all_ids = list_all_crawlers()
    for crawler_id in all_ids:
        if crawler_id not in active_ids:
            status = load_crawler_status(crawler_id)
            if status:
                results.append(status)

    # Sort by crawler_id (most recent first)
    results.sort(key=lambda x: x.get('crawler_id', ''), reverse=True)

    return results


def get_resumable_crawlers() -> list:
    """
    Get list of crawlers that can be resumed after interruption.

    Returns list of resumable crawler info.
    """
    return list_resumable_crawlers()


def resume_interrupted_crawler(crawler_id: str) -> dict:
    """
    Resume an interrupted crawler from its saved state.

    Returns the resumed crawler status or None if not found.
    """
    crawler = resume_crawler_from_disk(crawler_id)
    if not crawler:
        return None

    # Start the crawler
    crawler.start()

    return crawler.get_status()
