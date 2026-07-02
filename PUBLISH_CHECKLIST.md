# Apify Store publish checklist

Complete these steps in [Apify Console](https://console.apify.com) after the Actor code is ready.

## 1. Billing and payout (required to get paid)

1. **Settings → Billing** — add a payment method (needed for proxy usage during testing).
2. **Settings → Billing & payments → Payout details** — complete tax/identity info.
3. Payout invoices generate on the **11th of each month** for the previous month.

## 2. Push the Actor

```bash
npm install -g apify-cli
apify login
cd "/home/muhasinrashid/gaugerCodeBase/11Apify/Reddit Scraper"
apify push
```

## 3. Test as private Actor

Run these inputs in Console → Development → My Actors → **stallion-reddit-scraper**:

**Browse:**
```json
{"startUrls":[{"url":"https://www.reddit.com/r/python/new/"}],"maxItems":20,"maxComments":0,"proxy":{"useApifyProxy":true}}
```

**Search:**
```json
{"searches":["machine learning"],"searchCommunityName":"python","maxItems":20,"time":"month","proxy":{"useApifyProxy":true}}
```

**Post + comments (cartalkuk acceptance test from your log):**
```json
{"startUrls":[{"url":"https://www.reddit.com/r/cartalkuk/new/"}],"maxItems":20,"maxPostCount":20,"maxComments":10,"scrollTimeout":40,"includeNSFW":true,"proxy":{"useApifyProxy":true}}
```

## 4. Publication metadata

Console → Actor → **Publication → Display information**:

- Name: **Stallion Reddit Scraper**
- Store URL: https://apify.com/busy_evidence/stallion-reddit-scraper
- Category: Social media
- README: auto-synced from `README.md` on each `apify push`
- Add screenshots of input form + dataset preview

## 5. Monetization (Pay Per Event)

Console → **Publication → Monetization → Set up monetization**:

| Event | Price |
|-------|-------|
| `apify-actor-start` | ~$0.00005 |
| `apify-default-dataset-item` | **$0.003** (~$3.00 / 1,000 results) |

- Enable **Pay per event + usage** initially (passes platform/proxy costs to users while tuning).
- Set primary event = `apify-default-dataset-item`.

No charging code needed — `Actor.push_data()` auto-charges dataset items.

## 6. Publish to Store

Click **Publish to Store** when metadata is complete. Verify at https://apify.com/store.
