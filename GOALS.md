# Farm data goals

What the farm records are for, ranked by priority. Priority = data that must be captured from day one (it can't be back-filled) and what other goals depend on.

Status: ✅ done · 🟡 partial · ⬜ not started · 🔮 future

| # | Goal | Status | Data needed | Depends on |
|---|---|---|---|---|
| 1 | **Core log** — every planting and every harvest | 🟡 `Farming_Finca_Volcan.xlsx` (plantings, no harvests yet) | planting: crop, variety, bed, area (m²), n plants, sow/transplant date · harvest: date, planting, weight (kg), count | — |
| 2 | **Input records** — what was applied, how much, when, where | 🟡 dose logs in [garden-crops-bone-ash-sop-doses.md](garden-crops-bone-ash-sop-doses.md), [zucchini-trial-2026-president-f1.md](zucchini-trial-2026-president-f1.md), xlsx | date, planting/bed, input, quantity, unit | 1 |
| 3 | **Continuous harvest** — always something to eat and sell | ⬜ | actual days to maturity vs packet, harvest-window length, season (dry Dec–Apr / wet May–Nov) → planting calendar | 1 |
| 4 | **Best varieties** — yield/m² + taste, via trials | ⬜ | variety, taste/quality score (1–5), trial plots: ≥3 replicates, random placement, or tricot (rank 3 at a time) | 1 |
| 5 | **Sales & demand** — what to grow how much of | ⬜ | date, product, qty sold, price, unsold/wasted, channel | 1 |
| 6 | **Pests & diseases** — key pests, what worked, resistant varieties | ⬜ | date, planting, pest/disease, severity, action, result | 1 |
| 7 | **Input effectiveness** — do biochar, bone ash, urine pay off? | ⬜ | untreated control plots, input cost → yield difference, cost/kg | 1, 2 |
| 8 | **Soil health trend** | 🟡 pH tests (2026-08-30, xlsx) | pH, organic matter, ~2×/year per bed | — |
| 9 | **Weather** | ⬜ | rain gauge (daily mm), later station (temp, humidity) | — |
| 10 | **Family food supply** — kg/week per crop vs need | ⬜ | weekly family need per crop (harvest data from 1) | 1 |
| 11 | **Profit per crop / m² / labor hour** | 🔮 | input costs, labor minutes per task | 5 |
| 12 | **Own Volcán-adapted seed** | 🔮 | seed lots, germination tests, selected parent plants | 4 |
| 13 | **Harvest lot traceability** | 🔮 | lot code (crop + bed + date) on each sale | 1, 5 |
| 14 | **Organic certification readiness** (Panama Ley 8/2002, Decreto 121/2015) | 🔮 | 5+ years of complete input/activity records — mostly covered by 1, 2, 6 | 1, 2, 6 |

First database schema covers goals 1–10; 11–14 are added later as new tables.

## References

- Trials: [OSA on-farm variety trials](https://agsci.oregonstate.edu/biblio/farm-variety-trials-guide-organic-vegetable-herb-and-flower-producers), [tricot (PNAS 2019)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6410884)
- Continuous harvest: [ATTRA](https://www.ncat.org/publication/scheduling-vegetable-plantings-for-continuous-harvest/)
- Crop budgets: [Wiswall](https://growingformarket.com/articles/a-sensible-approach-to-crop-budgets)
- IPM records: [NRCS vegetable IPM guide](https://www.northeastipm.org/neipm/assets/File/NRCS-Resources/IPM-Plan-Guide-Sheet-Practices-for-Vegetable-Production.pdf)
- Seed selection: [Cornell](https://smallfarms.cornell.edu/2019/10/on-farm-variety-improvement-part-ii-selection-and-plant-breeding/)
- Traceability: [Cornell GAPs](https://cals.cornell.edu/national-good-agricultural-practices-program/resources/educational-materials/decision-trees/traceability)
- Organic law: [Ley 8 de 2002](https://docs.panama.justia.com/federales/leyes/8-de-2002-jan-30-2002.pdf)
