# Stallion Reddit Scraper

**Apify Store:** [busy_evidence/stallion-reddit-scraper](https://apify.com/busy_evidence/stallion-reddit-scraper)

Fast, lightweight Reddit scraper for Apify. Collect posts from subreddit listings, keyword search, and individual post URLs — **no Reddit login required**. Uses efficient HTTP requests instead of a headless browser, so runs are typically faster and cheaper.

> **Disclaimer:** This is an unofficial scraper and is not affiliated with Reddit Inc. Reddit may change access rules at any time. Use responsibly and respect Reddit's terms of service.

---

## Why use this Reddit Scraper?

| | This Actor | Typical browser scrapers |
|---|---|---|
| **Speed** | Seconds per listing page | Minutes (page render + scroll) |
| **Cost** | Low memory (256–1024 MB) | High memory (browser overhead) |
| **Proxy usage** | Residential proxy for listings | Residential + browser sessions |

**Best for:** monitoring subreddits, lead generation, sentiment pipelines, research datasets, and scheduled jobs where you need posts fast at predictable per-result pricing.

**For full comment threads and vote counts on every field**, set `maxComments` above `0` when JSON access is available, or use a browser-based scraper for maximum coverage.

---

## Features

- **Browse subreddits** — `new`, `hot`, `top`, `rising`, `controversial`
- **Keyword search** — global or scoped to one subreddit (`searchCommunityName`)
- **Single post URLs** — scrape one thread by URL
- **Nested comments** — when `maxComments > 0` (see limitations below)
- **Date filters** — `postDateLimit` / `commentDateLimit` (`YYYY-MM-DD`)
- **NSFW toggle** — `includeNSFW`
- **Pagination resume** — pass `?after=t3_…` in start URLs
- **Search → browse fallback** — empty niche search falls back to subreddit listing
- **RSS fallback** — when Reddit blocks JSON (common in 2026), listings use public Atom feeds automatically

---

## How it works

1. **Phase 1 — Discovery:** listing or search URLs are crawled; post stubs are collected.
2. **Phase 2 — Enrichment (optional):** when `maxComments > 0`, each post is fetched again for full body + comments.

**Data sources:**

| Source | When used | What you get |
|---|---|---|
| `json` | Reddit JSON API responds | Full fields: scores, comment counts, comments |
| `rss` | JSON blocked (403) | Title, body snippet, author, URL, date — `upVotes` and `numberOfComments` are `0`; rows include `"dataSource": "rss"` |

For listing-only runs, set **`maxComments: 0`** (default). This is the fastest and most reliable mode on Apify Cloud.

**Proxy:** enable Apify Proxy with residential IPs. Reddit blocks datacenter traffic quickly.

---

## How to use

1. Open this Actor on Apify Store and click **Try for free** (or run from your private Actor page).
2. Choose a mode:
   - **Subreddit listing** → add a URL like `https://www.reddit.com/r/python/new/`
   - **Search** → leave `startUrls` empty and fill `searches`
   - **One post** → paste a `/comments/` URL
3. Set **`maxItems`** (total results cap) and **`maxComments`** (`0` for posts only).
4. Enable **proxy** → `useApifyProxy: true` (residential recommended).
5. Click **Start** and download results as JSON, CSV, Excel, or via API.

---

## Input

Provide **either** `startUrls` **or** `searches`. When `startUrls` is set, search fields are ignored.

### Input parameters

| Field | Type | Default | Description |
|---|---|---|---|
| `startUrls` | array | — | Subreddit listings, post URLs, or paginated listing URLs |
| `searches` | array | `[]` | Keywords (used when `startUrls` is empty) |
| `searchCommunityName` | string | — | Restrict search to one subreddit (no `r/` prefix) |
| `sort` | string | `new` | `new`, `hot`, `top`, `relevance`, `comments` |
| `time` | string | `all` | `hour`, `day`, `week`, `month`, `year`, `all` |
| `postDateLimit` | string | — | Only posts on/after `YYYY-MM-DD` |
| `commentDateLimit` | string | — | Only comments on/after `YYYY-MM-DD` |
| `maxItems` | integer | `100` | Hard cap on dataset rows |
| `maxPostCount` | integer | `100` | Max posts per listing/search page |
| `maxComments` | integer | `0` | Comments per post; `0` = skip comment fetch |
| `scrollTimeout` | integer | `40` | Seconds to keep paginating a listing |
| `includeNSFW` | boolean | `false` | Include adult content |
| `searchPosts` | boolean | `true` | Search posts when using `searches` |
| `searchComments` | boolean | `false` | Search comments |
| `searchCommunities` | boolean | `false` | Search communities |
| `searchUsers` | boolean | `false` | Search users |
| `skipComments` | boolean | `false` | Skip comments even if `maxComments > 0` |
| `includeMediaLinks` | boolean | `false` | Add image/video URLs (slower) |
| `proxy` | object | — | Apify proxy config; residential recommended |

### Example — browse a subreddit (recommended)

```json
{
  "startUrls": [{ "url": "https://www.reddit.com/r/cartalkuk/new/" }],
  "maxItems": 100,
  "maxPostCount": 100,
  "maxComments": 0,
  "scrollTimeout": 40,
  "includeNSFW": true,
  "proxy": { "useApifyProxy": true }
}
```

### Example — search inside a subreddit

```json
{
  "searches": ["machine learning", "data science"],
  "searchCommunityName": "python",
  "sort": "new",
  "time": "year",
  "postDateLimit": "2024-01-01",
  "maxItems": 200,
  "maxComments": 0,
  "proxy": { "useApifyProxy": true }
}
```

### Example — one post with comments

```json
{
  "startUrls": [{
    "url": "https://www.reddit.com/r/python/comments/EXAMPLE/title_here/"
  }],
  "maxComments": 50,
  "proxy": { "useApifyProxy": true }
}
```

### Example — resume pagination

```json
{
  "startUrls": [{
    "url": "https://www.reddit.com/r/dashcam/new/?after=t3_abc123"
  }],
  "maxItems": 100,
  "proxy": { "useApifyProxy": true }
}
```

---

## Output

Each dataset row is one **post** with a consistent, structured schema.

### Post object

```json
{
  "dataType": "post",
  "parsedId": "abc123",
  "id": "t3_abc123",
  "url": "https://www.reddit.com/r/python/comments/abc123/title/",
  "title": "Example post title",
  "body": "Post selftext or empty for link posts",
  "parsedCommunityName": "python",
  "communityName": "r/python",
  "username": "reddit_user",
  "upVotes": 150,
  "numberOfComments": 42,
  "createdAt": "2025-08-01T12:00:00.000Z",
  "scrapedAt": "2026-07-01T12:00:00.000Z",
  "comments": [],
  "dataSource": "rss"
}
```

`dataSource` appears only when the row came from RSS fallback (`"rss"`). JSON-sourced rows omit this field.

### Comment object (when `maxComments > 0`)

```json
{
  "parsedId": "cmt1",
  "body": "Great post!",
  "username": "reader42",
  "upVotes": 3,
  "createdAt": "2025-08-01T12:05:00.000Z",
  "parentId": "t3_abc123"
}
```

With `includeMediaLinks: true`, posts may also include `imageUrls`, `videoUrls`, `flair`, `over18`, `isVideo`, and `upVoteRatio`.

---

## Pricing

This Actor uses **Pay per event** on Apify Store:

| Event | Typical price |
|---|---|
| Actor start | ~$0.00005 per run |
| Result (`apify-default-dataset-item`) | ~$0.003 per post |

Example: **100 posts ≈ $0.30** (+ small start fee). Platform/proxy usage may apply depending on your monetization settings.

Set a **max cost per run** in the Apify Console before large jobs.

---

## API usage

Replace `YOUR_TOKEN` with your [Apify API token](https://console.apify.com/account/integrations).

Actor ID: **`busy_evidence/stallion-reddit-scraper`**

### Python

```python
from apify_client import ApifyClient

client = ApifyClient("YOUR_TOKEN")

run = client.actor("busy_evidence/stallion-reddit-scraper").call(run_input={
    "startUrls": [{"url": "https://www.reddit.com/r/python/new/"}],
    "maxItems": 100,
    "maxComments": 0,
    "proxy": {"useApifyProxy": True},
})

items = client.dataset(run["defaultDatasetId"]).list_items().items
print(f"Scraped {len(items)} posts")
```

### JavaScript

```javascript
import { ApifyClient } from 'apify-client';

const client = new ApifyClient({ token: 'YOUR_TOKEN' });

const run = await client.actor('busy_evidence/stallion-reddit-scraper').call({
    startUrls: [{ url: 'https://www.reddit.com/r/python/new/' }],
    maxItems: 100,
    maxComments: 0,
    proxy: { useApifyProxy: true },
});

const { items } = await client.dataset(run.defaultDatasetId).listItems();
console.log(`Scraped ${items.length} posts`);
```

### cURL

```bash
curl -X POST \
  "https://api.apify.com/v2/acts/busy_evidence~stallion-reddit-scraper/runs?token=YOUR_TOKEN&waitForFinish=300" \
  -H "Content-Type: application/json" \
  -d '{
    "startUrls": [{"url": "https://www.reddit.com/r/python/new/"}],
    "maxItems": 100,
    "maxComments": 0,
    "proxy": {"useApifyProxy": true}
  }'
```

### Integrations

Export results to **Google Sheets**, **Slack**, **Zapier**, **Make**, or any webhook via Apify integrations on the run's **Export** tab.

---

## FAQ

**Why enable residential proxy?**  
Reddit blocks datacenter IPs. Apify residential proxy is required for reliable runs on the platform.

**Why is `maxComments` default 0?**  
Comment fetch needs the JSON API, which Reddit often blocks. Listing scans with `maxComments: 0` use RSS fallback and complete in seconds.

**Why are `upVotes` and `numberOfComments` zero?**  
When JSON is blocked, the Actor falls back to RSS feeds which do not include scores or comment counts. The row will have `"dataSource": "rss"`.

**What is `scrollTimeout`?**  
Seconds to keep paginating before stopping (default `40`). Increase for large subreddits or slow proxy regions.

**Why fewer results than `maxItems`?**  
Reddit caps listing depth at roughly 1,000 posts per sort. Date filters and NSFW settings also reduce counts.

**Does this scrape user profiles?**  
Not yet. Supported start URLs are subreddit listings (`/r/{sub}/{sort}`) and post URLs (`/r/{sub}/comments/{id}`).

---

## Limitations

- Reddit JSON API access is restricted for unauthenticated clients (2026). Listings use RSS when needed.
- RSS rows lack vote/comment counts and cannot fetch comment threads.
- Historical listing depth is ~1,000 items per sort — use `postDateLimit` + scheduled runs for ongoing monitoring.
- Search and comment modes depend on JSON availability and may return fewer fields than browser-based scrapers.

---

## Local development

```bash
pip install -r requirements.txt
python -m pytest tests/
apify run --input='{"startUrls":[{"url":"https://www.reddit.com/r/python/new/"}],"maxItems":5,"maxComments":0}'
```

---

## Changelog

### 0.1.8
- RSS/Atom fallback when Reddit JSON returns 403
- `dataSource: "rss"` on fallback rows
- Apify `Actor.log` for visible platform logs

### 0.1.0
- Initial release: browse, search, and post scraping
