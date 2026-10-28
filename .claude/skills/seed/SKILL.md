---
name: seed
description: Deep worldwide literature search for the best seed variety of a crop for Volcán, Chiriquí (taste + climate fit), then an extensive search for the most trustworthy, cheapest seller, weighing shops already chosen in seeds-to-buy.md. Use when the user runs /seed <crop> or asks which variety of a crop to buy and where.
---

# Best seed for Volcán + cheapest trustworthy seller

The crop (and any constraints, e.g. "curly", "for sauce", "bush type") is whatever the user typed after `/seed`. Run both parts: **A. variety research**, then **B. seller and price research**.

## Context (don't re-ask)

- **Site:** Volcán, Chiriquí, Panama, about 1,400 m.
  - 16–24 °C, about 4,400 mm rain a year (wet May–Nov, dry roughly Dec–Apr), 74–94% humidity.
  - Barú volcanic-ash Andisol, pH about 6.6.
  - Day length 11.6–12.6 h all year: short days, no winter cold.
- **Growing:** organic, family use plus **small-quantity sales**. Marketability (yield, shelf life, looks, bunch quality) counts alongside taste.
- **Read first:** `seeds-to-buy.md` for shops already in the order, and any existing `<crop>-*.md` file in the repo, so you build on prior research instead of repeating it.

## Tools

- Use **Exa** (`web_search_exa`, `web_fetch_exa`) and **WebSearch/WebFetch** on every run. Fetch full papers for key sources; don't trust abstracts or snippets for numbers.
- If Exa rate-limits, `sleep 30` / 60 / 120 and retry; do web-search work meanwhile. Fall back to web only after 3 failures and say so.
- For live stock, price and shipping, use the **chrome-devtools MCP** (Chrome on :9222) when WebFetch gets 403 or Cloudflare pages. Park Seed and Hazzard's block WebFetch.
  - **Shopify stores** (Paramount, Park, growitalian): fetch `/products/<handle>.js` from inside the page for variant prices and `available`, and `/search/suggest.json?q=...&resources[type]=product` to search.
  - **Johnny's** (Salesforce): size swatches carry `sizecode`; the SKU is `<item>.<sizecode>` (e.g. `3513.26` = 1 oz).

## A. Variety research

Search worldwide, in several languages (English, Spanish, Portuguese, Polish/German/Dutch for herbs and brassicas, Japanese for squash, etc.). Cover these angles separately:

1. **Replicated cultivar trials:** university, extension, CGIAR or AVRDC/WorldVeg, Embrapa, INTA, IDIAP. Priority order: tropical highland (Kenya, Ethiopia, Colombia, Costa Rica, Guatemala, Brazil's cool regions), then subtropical, then temperate.
2. **Taste:** sensory panels, Brix/acid, consumer tests, chef trials (e.g. Row 7, Culinary Breeding Network), and seed-company trial notes. Label anecdotes as anecdotes.
3. **Disease under wet, humid conditions:** the main limit in Volcán. Look for cultivar resistance ratings (HR/IR codes) and seed-borne pathogens with seed-treatment advice.
4. **Climate physiology:** day-length and vernalization needs (short days with no cold change bolting and bulbing), heat or cool tolerance, and flowering and pollination at 16–24 °C.
5. **Open-pollinated vs F1:** whether the variety is true to seed and whether saving seed is practical (isolation, cross-pollination).
6. **Organic and low-input performance:** OSSI, organic trials, untreated seed.

### Rigor rules (learned the hard way)

- **Check statistics before claiming "X beats Y."** Compare the difference with the LSD or Tukey letters. If it isn't significant, say "tied." Report each year separately when years disagree.
- State the trial design: replicated or not, number of years and sites, harvest method (one cut vs repeated cuts), and the climate it ran in.
- **Never rank two varieties as if they were compared when they weren't in the same trial.** Say so explicitly.
- Separate the evidence types: trial data, seed-company claims, and grower anecdote.
- If the evidence can't separate the top picks, say so and recommend a **side-by-side trial in the user's own beds**.
- Correct earlier claims in repo files when new evidence contradicts them.

## B. Seller and price research

1. **Candidates:**
   - Shops already in `seeds-to-buy.md`: Johnny's, Paramount Seeds, Hazzard's (Hazwho store), Park Seed, Seedway, growitalian, AgroEnlace (Panama).
   - Specialty and origin sellers for the variety: Kitazawa (Japanese), Baker Creek, True Leaf, Fedco, High Mowing, Territorial, Osborne, Harris, Stokes, Seed Savers, Reimer, Rohrer, Holmes, Mary's Heirloom.
   - Local Panama and Costa Rica sources, where they exist.
2. **Avoid** China-based copycat resellers (SeedsDay, Bestseedshop, Aeseeds and look-alikes) and unknown Amazon or eBay sellers. Check reputation (Trustpilot, Garden Watchdog) for any shop not already used.
3. For each candidate, record:
   - pack size, seeds per pack (convert by weight using seeds/oz from the seller or Johnny's), and price
   - **live stock status** (check in Chrome)
   - untreated or organic status
   - shipping
4. **Compare total delivered cost, not sticker price.** Shipping is per order:
   - **Park Seed:** $6.95 flat for seed-only orders.
   - **Seedway:** $20 flat per order, any size (verified at checkout).
   - **Paramount:** free shipping only over $300; ships internationally at buyer's risk.
   - **Johnny's:** international orders need a $500 minimum and a phytosanitary certificate, so ship to a US mailbox (Aeropost, MiCasillero, Miami). Florida sales tax may apply.
   - A shop already in the order costs **$0 extra shipping**. Weigh that heavily: a slightly pricier seed in an existing box often beats a cheaper seed that needs a new order.
5. Size the quantity for family use plus small sales, against the seed's viability in years. Don't push bulk packs unless the per-seed saving survives shipping.
6. To learn shipping, you may add an item to a cart and step through checkout **without placing the order**, then **remove it** and tell the user. Only leave items in a cart when the user asks.

## Output

- **Bottom line first:** the pick, whether it's clearly better or effectively tied, and the shop to buy from.
- **Variety synthesis by theme** (yield, taste, disease, climate fit, OP/F1), covering agreements, disagreements and gaps.
- **Ranking table:** rank, variety, why, caveat.
- **Seller table:** shop, pack, seeds, price, shipping, total, stock (with date), untreated or organic, link.
- **Recommendation** that accounts for the existing `seeds-to-buy.md` orders.
- **Key sources table:** title, authors/org, year, takeaway, link. End with a sources list.
- Offer to add the pick to `seeds-to-buy.md` (and to the shop's cart). If the user agrees, edit the file, then commit and push.
