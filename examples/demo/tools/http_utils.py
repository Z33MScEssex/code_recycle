"""Small HTTP helpers used across demo projects."""
import json
import time
import urllib.error
import urllib.request


def get_json(url, timeout=10):
    """Download a URL and parse the JSON reply."""
    with urllib.request.urlopen(url, timeout=timeout) as reply:
        return json.loads(reply.read().decode("utf-8"))


def retry(call, tries=3, first_wait=1.0):
    """Run call(); if it raises a network error, wait and try again, doubling the wait each time."""
    wait = first_wait
    for attempt in range(1, tries + 1):
        try:
            return call()
        except urllib.error.URLError:
            if attempt == tries:
                raise
            time.sleep(wait)
            wait *= 2
