"""
Flask API Server for Web Crawler & Search Engine

Endpoints:
    POST /crawler/create     - Create and start a new crawler
    GET  /crawler/list       - List all crawlers
    GET  /crawler/status/<id> - Get crawler status
    GET  /crawler/logs/<id>  - Get crawler logs (long-polling)
    POST /crawler/pause/<id> - Pause a crawler
    POST /crawler/resume/<id> - Resume a crawler
    POST /crawler/stop/<id>  - Stop a crawler
    GET  /search             - Search the index
    GET  /stats              - Get index statistics
"""

from flask import Flask, request, jsonify, send_from_directory
from services.crawler_service import (
    create_new_crawler,
    get_crawler_status,
    get_crawler_logs,
    pause_crawler,
    resume_crawler,
    stop_crawler,
    get_all_crawlers,
    get_resumable_crawlers,
    resume_interrupted_crawler
)
from utils.crawler_job import clear_inactive_crawlers, clear_all_crawlers
from services.search_service import search, search_with_details, get_index_stats
from utils.storage import clear_visited_urls, clear_visited_urls_by_domain

app = Flask(__name__, static_folder='demo')


# =============================================================================
# Crawler Endpoints
# =============================================================================

@app.route('/crawler/create', methods=['POST'])
def api_create_crawler():
    """Create and start a new crawler job."""
    try:
        data = request.get_json() or {}

        origin = data.get('origin', '')
        max_depth = int(data.get('max_depth', 2))
        hit_rate = float(data.get('hit_rate', 50.0))
        max_queue_capacity = int(data.get('max_queue_capacity', 1000))
        max_urls_to_visit = int(data.get('max_urls_to_visit', 100))

        status = create_new_crawler(
            origin=origin,
            max_depth=max_depth,
            hit_rate=hit_rate,
            max_queue_capacity=max_queue_capacity,
            max_urls_to_visit=max_urls_to_visit
        )

        return jsonify({
            'success': True,
            'crawler': status
        })

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/crawler/list', methods=['GET'])
def api_list_crawlers():
    """List all crawlers."""
    crawlers = get_all_crawlers()
    return jsonify({
        'success': True,
        'crawlers': crawlers
    })


@app.route('/crawler/status/<crawler_id>', methods=['GET'])
def api_crawler_status(crawler_id):
    """Get status of a specific crawler."""
    status = get_crawler_status(crawler_id)
    if status:
        return jsonify({
            'success': True,
            'status': status
        })
    return jsonify({
        'success': False,
        'error': 'Crawler not found'
    }), 404


@app.route('/crawler/logs/<crawler_id>', methods=['GET'])
def api_crawler_logs(crawler_id):
    """
    Get crawler logs.
    Supports long-polling via 'since' parameter.
    """
    last_n = request.args.get('last_n', 50, type=int)
    logs = get_crawler_logs(crawler_id, last_n=last_n)

    return jsonify({
        'success': True,
        'logs': logs
    })


@app.route('/crawler/pause/<crawler_id>', methods=['POST'])
def api_pause_crawler(crawler_id):
    """Pause a running crawler."""
    success = pause_crawler(crawler_id)
    return jsonify({
        'success': success,
        'message': 'Crawler paused' if success else 'Could not pause crawler'
    })


@app.route('/crawler/resume/<crawler_id>', methods=['POST'])
def api_resume_crawler(crawler_id):
    """Resume a paused or stopped crawler."""
    result = resume_crawler(crawler_id)
    return jsonify(result)


@app.route('/crawler/stop/<crawler_id>', methods=['POST'])
def api_stop_crawler(crawler_id):
    """Stop a crawler."""
    success = stop_crawler(crawler_id)
    return jsonify({
        'success': success,
        'message': 'Crawler stopped' if success else 'Could not stop crawler'
    })


@app.route('/crawler/clear-visited', methods=['POST'])
def api_clear_visited():
    """
    Clear visited URLs.

    Body params:
        domain: (optional) Only clear URLs containing this domain
    """
    data = request.get_json() or {}
    domain = data.get('domain', '')

    if domain:
        count = clear_visited_urls_by_domain(domain)
        message = f'Cleared {count} URLs matching "{domain}"'
    else:
        count = clear_visited_urls()
        message = f'Cleared all {count} visited URLs'

    return jsonify({
        'success': True,
        'cleared': count,
        'message': message
    })


@app.route('/crawler/clear-registry', methods=['POST'])
def api_clear_registry():
    """
    Clear crawler registry (remove inactive/deleted crawlers from memory).

    Body params:
        all: (optional) If true, clear all crawlers from registry
    """
    data = request.get_json() or {}
    clear_all = data.get('all', False)

    if clear_all:
        count = clear_all_crawlers()
        message = f'Cleared all {count} crawlers from registry'
    else:
        count = clear_inactive_crawlers()
        message = f'Cleared {count} inactive crawlers from registry'

    return jsonify({
        'success': True,
        'cleared': count,
        'message': message
    })


@app.route('/crawler/resumable', methods=['GET'])
def api_resumable_crawlers():
    """
    List crawlers that can be resumed after interruption.

    These are crawlers that were running or paused when the server was stopped.
    """
    crawlers = get_resumable_crawlers()
    return jsonify({
        'success': True,
        'resumable': crawlers
    })


@app.route('/crawler/resume-interrupted/<crawler_id>', methods=['POST'])
def api_resume_interrupted(crawler_id):
    """
    Resume an interrupted crawler from its saved state.

    This restores the queue and stats, then continues crawling.
    """
    status = resume_interrupted_crawler(crawler_id)
    if status:
        return jsonify({
            'success': True,
            'message': 'Crawler resumed from saved state',
            'crawler': status
        })
    return jsonify({
        'success': False,
        'error': 'Crawler not found or cannot be resumed'
    }), 404


# =============================================================================
# Search Endpoints
# =============================================================================

@app.route('/search', methods=['GET'])
def api_search():
    """
    Search the index.

    Query params:
        q or query: Search query
        page: Page number (default 1)
        page_size: Results per page (default 10)
        sortBy: Sorting method (default 'relevance' - sorts by frequency)
    """
    query = request.args.get('query', '') or request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 10, type=int)
    sort_by = request.args.get('sortBy', 'relevance')

    result = search_with_details(query, page=page, page_size=page_size)

    return jsonify({
        'success': True,
        'query': query,
        'sortBy': sort_by,
        **result
    })


@app.route('/stats', methods=['GET'])
def api_stats():
    """Get index statistics."""
    stats = get_index_stats()
    return jsonify({
        'success': True,
        'stats': stats
    })


# =============================================================================
# Static Files (Frontend)
# =============================================================================

@app.route('/')
def index():
    """Redirect to search page."""
    return send_from_directory('demo', 'search.html')


@app.route('/crawler')
def crawler_page():
    """Serve crawler creation page."""
    return send_from_directory('demo', 'crawler.html')


@app.route('/status')
def status_page():
    """Serve status dashboard page."""
    return send_from_directory('demo', 'status.html')


@app.route('/demo/<path:filename>')
def serve_demo(filename):
    """Serve static files from demo folder."""
    return send_from_directory('demo', filename)


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':
    print("Starting Web Crawler & Search Engine API Server...")
    print("URL: http://localhost:3600")
    print("\nEndpoints:")
    print("  - GET  /              -> Search page")
    print("  - GET  /crawler       -> Crawler creation page")
    print("  - GET  /status        -> Status dashboard")
    print("  - POST /crawler/create")
    print("  - GET  /crawler/list")
    print("  - GET  /crawler/status/<id>")
    print("  - GET  /search?q=<query>")
    app.run(host='0.0.0.0', port=3600, debug=True)
