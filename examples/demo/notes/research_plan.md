# Demo project: research plan

## Topic 1: Read a TOML settings file

**Question:** how do I read a settings file without installing anything?

- **URL:** https://docs.python.org/3/library/tomllib.html
- **Where on the page:** "Examples", the first example.
- **What it taught:** tomllib is in the standard library from Python 3.11. The file must be opened in binary mode.
- **Code pattern from source:**
```python
import tomllib

with open("pyproject.toml", "rb") as f:
    data = tomllib.load(f)
```

## Topic 2: Retry a network call

**Question:** how long should I wait between retries?

- **URL:** https://docs.python.org/3/library/urllib.error.html
- **Where on the page:** `URLError`.
- **What it taught:** URLError covers network problems, so it's the one to retry on. A wait that doubles each time avoids hammering a struggling server.
- **Code pattern from source:** see `tools/http_utils.py`, `retry`.
