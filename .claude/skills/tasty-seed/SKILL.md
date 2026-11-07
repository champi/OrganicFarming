---
name: tasty-seed
description: Worldwide search for the best-tasting varieties of a crop (competition winners, sensory-panel and chef favorites, cult heirlooms) that can be grown in Volcán, Chiriquí, in a hot tunnel, high tunnel, greenhouse or other protected setup, or outdoors as a bonus. Taste is the number one factor. Then finds the most trustworthy, cheapest seller. Use when the user runs /tasty-seed <crop> or asks for the tastiest variety of a crop.
---

# Tastiest seed for Volcán (protected growing allowed)

**Depth rule:** research must be **wide, deep and extensive**. Run many searches (aim for 40+ queries across Exa and the web) in many languages, and fetch full pages. Keep searching until new sources stop adding candidates or evidence. Don't stop at the first good answer.

The crop (and any constraints) is whatever the user typed after `/tasty-seed`. **Taste comes first.** Climate fit is a filter, not the ranking factor. A variety that needs a tunnel is fine. Run **A. taste research**, then **B. growability in Volcán**, then **C. seller and price research**.

## Context (don't re-ask)

- **Site:** Volcán, Chiriquí, Panama, about 1,400 m.
  - 16–24 °C, about 4,400 mm rain a year (wet May–Nov, dry roughly Dec–Apr), 74–94% humidity.
  - Barú volcanic-ash Andisol, pH about 6.6.
  - Day length 11.6–12.6 h all year: no long days and no winter cold.
- **Growing:** organic, family use plus small-quantity sales. A standout taste is itself a selling point.
- **Read first:** `seeds-to-buy.md` and any existing `<crop>-*.md` file in the repo.
- **Tools:** same as the `/seed` skill (`.claude/skills/seed/SKILL.md`). That means Exa plus WebSearch/WebFetch on every run, Exa retry/backoff, and chrome-devtools for live stock and price.

## A. Taste research (main effort)

Search worldwide and in several languages (English, Spanish, French, Italian, German, Dutch, Polish, Japanese, Korean and others as the crop needs). Look for:

1. **Competitions and awards:**
   - Tomato and heirloom tasting contests (e.g. Tomatofest, Heirloom Expo, Carmel TomatoFest, local "best tasting" fairs).
   - All-America Selections and Fleuroselect winners (note when the award was for taste rather than for looks or yield).
   - Slow Food Ark of Taste and Presidia.
   - Japanese and Korean premium-fruit grading.
   - Fair and show winners.
2. **Sensory science:**
   - Trained panels and consumer preference tests.
   - Brix, sugar/acid ratio and volatile profiles (e.g. Klee lab at the University of Florida for tomato and strawberry).
   - **Check the statistics:** see the rigor rules in `/seed`.
3. **Chefs and breeders:** Row 7, Culinary Breeding Network (Variety Showcase), Michelin and farm-to-table chef picks, and breeder notes.
4. **Grower anecdotes worldwide (search hard):**
   - Forums: Tomatoville, GardenWeb/Houzz, Reddit (r/gardening, r/tomatoes, r/vegetablegardening, country subs), OpenAg.
   - Non-English forums: e.g. forum.gardenia.pl, Ogrodowisko, Mein schöner Garten, Hortus Focus, Forum Orto, Jardinage Forum, Infojardín, 2ch/Yahoo Chiebukuro.
   - Blogs, YouTube taste tests, Facebook groups, and trial reports from tropical or highland growers (Costa Rica, Colombia, Kenya, Hawaii).
   - **Seed-store product reviews:** customer reviews and star ratings on Baker Creek, Johnny's, Territorial, Tomatofest and similar shops, plus Trustpilot and Garden Watchdog. Pull out what reviewers say about taste and how the plant grew in humid or warm climates.
   - Tally recurring praise and complaints across sources. Label all of this as **anecdote or claim**, not data.
5. **Regional legends:** origin-protected or cult varieties (DOP/PDO, heirlooms from Italy, France, Japan, Mexico and elsewhere).

For each variety, state **why** it tastes better (sugar, acid, aroma, texture, an abundance of a key volatile) and where that claim comes from.

## B. Growability in Volcán (filter, not ranking)

For each top-taste candidate, judge which settings would let it produce well here:

- **Outdoor:** works as-is in the wet or dry season.
- **Rain shelter or high tunnel:** keeps rain off the leaves, which cuts fungal and bacterial disease, the main limit in Volcán.
- **Hot tunnel or greenhouse:** adds heat for crops that want more than 16–24 °C (melons, peppers, eggplant, basil, some tomatoes).
- **Other:** shade cloth, raised beds, containers, or hand pollination when pollinators can't get in.

Also check:

- Day-length or vernalization needs that short days with no cold can't meet (e.g. long-day onions, strawberries that need chilling).
- Disease under high humidity, even under cover (botrytis, powdery mildew).
- Whether flavor holds up at Volcán's temperatures. Low heat can cut sugars and aroma in some crops, while cool nights raise Brix in others. Cite evidence where it exists.

Drop varieties that can't work here even with protection, and say why.

## C. Seller and price research

Follow `/seed` section B exactly: candidate shops, shops to avoid, delivered-cost comparison, shipping rules, quantity sizing, and the cart policy. Heirloom specialists matter more for this skill:

- Tomatofest, Baker Creek, Seed Savers, Adaptive Seeds, Wild Boar Farms, Row 7.
- Italian, French and Japanese origin sellers.

## Output (short)

- **Bottom line:** the tastiest pick that works here, the growing setup it needs, and the shop to buy from.
- **Taste ranking table:** rank, variety, taste evidence (with its type: competition, panel or anecdote), setup needed in Volcán, caveat.
- **Seller table** (same columns as `/seed`).
- **Sources list.**
- Offer to add the pick to `seeds-to-buy.md`. If the user agrees, edit the file, then commit and push.
