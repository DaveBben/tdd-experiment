## Task
**Task Statement: Restore Anchor Initialization and Rate-Limit Scheduling**

Restore `AnchorCheckParser.__init__` and
`HyperlinkAvailabilityCheckWorker.limit_rate`. The parser initializes an exact,
case-sensitive search for `id` or `name` on any start tag. The worker turns an optional
numeric or HTTP-date `Retry-After` value into a retry timestamp, otherwise applies the
per-origin default/exponential-backoff rules and timeout below. Request execution,
redirect handling, response streaming and the rest of link validation are outside these
two interfaces.

## Interface Descriptions

### Interface Description 1
Below is **Interface Description 1**

Path: `/testbed/sphinx/builders/linkcheck.py`
```python
class AnchorCheckParser(HTMLParser):
    """Specialised HTML parser that looks for a specific anchor."""

    def __init__(self, search_anchor: str) -> None:
        """
        Initialize an AnchorCheckParser instance for searching a specific anchor in HTML content.
        
        This parser extends HTMLParser to look for a matching 'id' or 'name' attribute
        on any HTML start tag; the tag itself need not be an `<a>` element.
        
        Parameters
        ----------
        search_anchor : str
            The anchor name/ID to search for in the HTML content. This should be the
            fragment part of a URL (the part after '#') that identifies a specific
            location within an HTML document.
        
        Attributes
        ----------
        search_anchor : str
            Stores the anchor name being searched for
        found : bool
            Boolean flag indicating whether the target anchor has been found during
            parsing. Initially set to False and becomes True when a matching anchor
            is discovered.
        
        Notes
        -----
        - The parser will search for both 'id' and 'name' attributes in HTML tags
        - Once the target anchor is found, the 'found' attribute is set to True
        - This parser is typically used in conjunction with HTTP response content
          to verify that anchor links point to valid locations within documents
        - The search is case-sensitive and looks for exact matches
        """
        # <your code>

class HyperlinkAvailabilityCheckWorker(Thread):
    """A worker class for checking the availability of hyperlinks."""

    def limit_rate(self, response_url: str, retry_after: str | None) -> float | None:
        """
        Implements rate limiting for HTTP requests to prevent overwhelming servers.
        
        This method handles HTTP 429 (Too Many Requests) responses by implementing
        exponential backoff with configurable timeout limits. It parses the server's
        Retry-After header to determine appropriate delay times and manages rate
        limiting state per network location.
        
        Parameters
        ----------
        response_url : str
            The URL of the HTTP response that triggered rate limiting. Used to
            extract the network location (netloc) for rate limit tracking.
        retry_after : str | None
            The value of the Retry-After header from the HTTP response. Can be:
            - A number of seconds to wait (as string)
            - An HTTP-date indicating when to retry
            - None if no Retry-After header was present
        
        Returns
        -------
        float | None
            The timestamp (in seconds since epoch) when the next check should be
            attempted. Returns None if the maximum rate limit timeout has been
            exceeded, indicating the URL should be marked as broken rather than
            retried.
        
        Notes
        -----
        - Uses exponential backoff strategy, doubling the delay time on each
          subsequent rate limit encounter for the same network location
        - Respects the server's Retry-After header when provided
        - Falls back to DEFAULT_DELAY (60.0 seconds) for new rate limits
        - Rate limits are tracked per network location (netloc) to avoid
          affecting other domains
        - For history-based backoff, if delay exceeds `rate_limit_timeout`, returns
          None to indicate the link should be considered broken
        - Updates the internal rate_limits dictionary with new RateLimit objects
          containing delay and next_check timestamp information
        """
        # <your code>
```

Additional information:
- A numeric `Retry-After` schedules `now + delay`; a valid HTTP-date schedules that
  timestamp and records its difference from `now`. Invalid header values fall back like a
  missing header.
- Without a usable header, a new origin waits 60 seconds and a repeated origin doubles its
  previous delay. If doubling first crosses `rate_limit_timeout`, schedule one retry exactly
  at that limit; if the resulting history-based delay is still over the limit, return `None`.
- A successfully parsed server header is not capped by this local timeout. Every successful
  schedule records its delay and timestamp for the response URL's network location and
  returns that timestamp.

Remember, **the interface template above is extremely important**. You must generate callable interfaces strictly according to the specified requirements, as this will directly determine whether you can pass our tests. If your implementation has incorrect naming or improper input/output formats, it may directly result in a 0% pass rate for this case.
