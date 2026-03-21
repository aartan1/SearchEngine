"""
HTML Parser using Python's native html.parser module.

Extracts:
- Page title
- Body text (words)
- Links (href attributes)
"""

from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import re


class WebPageParser(HTMLParser):
    """
    Custom HTML parser to extract title, text content, and links.
    """

    # Tags to ignore (don't extract text from these)
    # Note: Only include tags that have closing tags. Self-closing tags (meta, link, br, img, etc.)
    # should NOT be here as they would increment ignore_depth without decrementing.
    IGNORE_TAGS = {'script', 'style', 'noscript', 'iframe', 'svg', 'head'}

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.title = ""
        self.links = []
        self.words = []

        # Parser state
        self._in_title = False
        self._in_body = False
        self._ignore_depth = 0  # Track nested ignored tags
        self._current_tag = None

    def handle_starttag(self, tag: str, attrs: list):
        self._current_tag = tag.lower()

        if self._current_tag == 'title':
            self._in_title = True

        if self._current_tag == 'body':
            self._in_body = True

        if self._current_tag in self.IGNORE_TAGS:
            self._ignore_depth += 1

        # Extract links from <a href="...">
        if self._current_tag == 'a':
            for attr_name, attr_value in attrs:
                if attr_name == 'href' and attr_value:
                    self._process_link(attr_value)

    def handle_endtag(self, tag: str):
        tag = tag.lower()

        if tag == 'title':
            self._in_title = False

        if tag == 'body':
            self._in_body = False

        if tag in self.IGNORE_TAGS and self._ignore_depth > 0:
            self._ignore_depth -= 1

        self._current_tag = None

    def handle_data(self, data: str):
        # Extract title text
        if self._in_title:
            self.title += data.strip()

        # Extract body text (when not inside ignored tags)
        if self._in_body and self._ignore_depth == 0:
            text = data.strip()
            if text:
                # Extract words from text
                extracted = self._extract_words(text)
                self.words.extend(extracted)

    def _process_link(self, href: str):
        """Process and normalize a link."""
        # Skip non-http links
        if href.startswith(('#', 'javascript:', 'mailto:', 'tel:', 'data:')):
            return

        # Convert relative URLs to absolute
        absolute_url = urljoin(self.base_url, href)

        # Only keep http/https links
        parsed = urlparse(absolute_url)
        if parsed.scheme in ('http', 'https'):
            # Remove fragment
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                clean_url += f"?{parsed.query}"
            self.links.append(clean_url)

    def _extract_words(self, text: str) -> list:
        """Extract valid words from text (letters and numbers only)."""
        # Split on non-alphanumeric characters
        tokens = re.split(r'[^a-zA-Z0-9]+', text.lower())
        # Filter empty strings and single characters
        return [word for word in tokens if len(word) > 1]

    def get_results(self) -> dict:
        """Get parsing results."""
        return {
            'title': self.title,
            'links': list(set(self.links)),  # Deduplicate links
            'words': self.words
        }


def parse_html(html_content: str, base_url: str) -> dict:
    """
    Parse HTML content and extract title, links, and words.

    Args:
        html_content: Raw HTML string
        base_url: Base URL for resolving relative links

    Returns:
        dict with keys: title, links, words
    """
    parser = WebPageParser(base_url)
    try:
        parser.feed(html_content)
    except Exception:
        # Handle malformed HTML gracefully
        pass
    return parser.get_results()


def count_word_frequencies(words: list) -> dict:
    """
    Count frequency of each word.

    Args:
        words: List of words

    Returns:
        dict mapping word -> frequency
    """
    freq = {}
    for word in words:
        freq[word] = freq.get(word, 0) + 1
    return freq
