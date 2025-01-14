# shared-timeout-requests
This module provides a method to create a context that shares a total timeout between requests.

```Python
@shared_timeout(timeout=3)
def requests_sequence(*urls):
    results = []
    for url in urls:
        result = requests.post(url)
        results.append(result)
    return results
```

## Installation

```bash
python -m pip install shared-timeout-requests
```
