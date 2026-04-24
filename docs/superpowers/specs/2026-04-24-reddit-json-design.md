# Reddit Collector Public JSON — Design

**Date:** 2026-04-24
**Phase:** 1 (collector pipeline)
**Status:** Draft for review

## Goal

Remove Reddit OAuth from the collector and rely exclusively on Reddit's public
listing endpoint at `https://www.reddit.com/r/{subreddit}/{sort}.json`.

The immediate motivation is operational: new Reddit app credentials are no
longer available for this project, so the collector must work without
`REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`.

## Design decisions

| #   | Decision                                                                                                                                   |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | **Transport:** public `.json` listing only. No OAuth fallback, no dual-mode config.                                                        |
| 2   | **Config surface:** keep `subreddit`, `sort`, `time_filter`, `limit`, `flair_filter`, and `user_agent`; remove credential fields entirely. |
| 3   | **Parsing contract:** keep the existing `children[*].data` parsing and `CollectorItem` shape unchanged.                                    |
| 4   | **Failure behavior:** if the listing request fails, log and return `[]`; if one post is malformed, skip only that post.                    |
| 5   | **Migration:** remove Reddit credential env vars and any OAuth wording from tests and docs touched by this change.                         |

## Request model

The collector requests:

```text
GET https://www.reddit.com/r/{subreddit}/{sort}.json
```

with query params:

- `limit=<reddit.limit>`
- `t=<reddit.time_filter>`

and header:

- `User-Agent: <reddit.user_agent>`

No `Authorization` header is sent.

`sort` continues to come from config. For the current config this produces the
effective endpoint:

```text
https://www.reddit.com/r/GlobalOffensive/hot.json?limit=25
```

when `sort: hot` and `limit: 25` are set in `config.yaml`.

## Code changes

### `overpass/collectors/reddit.py`

- Remove token state from `RedditCollector` (`_access_token`,
  `_token_expires_at`).
- Remove `_get_access_token(...)` entirely.
- Replace the OAuth base URL with the public Reddit base URL.
- Update `collect()` so it fetches posts directly without checking for missing
  credentials.
- Keep `_parse_post(...)` unchanged unless a test reveals a `.json`-specific
  payload difference that must be handled.

Target flow:

```python
async def collect(self) -> list[CollectorItem]:
    config = load_config()
    reddit_cfg = config.reddit

    try:
        posts = await self._fetch_posts(reddit_cfg)
    except Exception:
        self.logger.exception("Failed to fetch Reddit posts")
        return []

    items: list[CollectorItem] = []
    for post in posts:
        try:
            item = self._parse_post(post, reddit_cfg.flair_filter)
            if item is not None:
                items.append(item)
        except Exception:
            self.logger.exception("Failed to parse Reddit post")

    return items
```

### `overpass/config.py`

Remove from `RedditConfig`:

```python
client_id_env: str = "REDDIT_CLIENT_ID"
client_secret_env: str = "REDDIT_CLIENT_SECRET"
```

No replacement fields are introduced.

### `config.yaml`

Remove the Reddit credential entries from the `reddit:` block.

### `.env`

Remove:

```text
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
```

The collector should require no Reddit-specific secrets after this change.

## Testing

`tests/test_reddit_collector.py` should be rewritten around the new public JSON
contract.

Keep:

- flair filtering coverage
- item field mapping coverage
- reddit video/media URL extraction
- self thumbnail suppression
- empty listing behavior
- fetch failure behavior
- malformed post skip behavior

Remove:

- OAuth token acquisition test
- auth failure test
- missing credentials skip test
- token caching test

Add:

- one fetch-path test that verifies the collector requests the public listing
  endpoint with `limit`, `t`, and `User-Agent`
- one collection test proving the collector no longer depends on Reddit
  credentials being present in config

## Error handling

The public listing endpoint is less explicit than OAuth-backed API access, so
the collector should remain conservative:

- network or HTTP failure: log exception, return `[]`
- malformed top-level payload: treat as empty list unless `raise_for_status()` or
  JSON decoding raises first
- malformed individual post: log exception, skip that post, continue

No retry loop is added in this change.

## What this design avoids

- dual transport support
- new feature flags or compatibility shims
- introducing Reddit-specific rate-limit state or caches
- broad collector refactors unrelated to transport/auth removal

