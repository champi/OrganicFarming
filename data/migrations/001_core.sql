-- Core schema for goals 1–10 in GOALS.md.
-- Principle: only what's needed to identify a record is required; everything else is optional
-- and can be filled in later. New columns/tables are added by later migrations.
-- Rules (CLAUDE.md): STRICT tables, INTEGER PRIMARY KEY, ISO dates checked with date().

-- ── Reference tables ────────────────────────────────────────────────

CREATE TABLE beds (                       -- where things grow
  id        INTEGER PRIMARY KEY,
  name      TEXT NOT NULL UNIQUE,         -- e.g. 'Raised bed baru 2', 'Entrance mounds row 1-4'
  site      TEXT CHECK (site IN ('farm','rented_house')),
  kind      TEXT CHECK (kind IN ('raised_bed','mound_row','field','tunnel','pot','other')),
  area_m2   REAL CHECK (area_m2 > 0),
  notes     TEXT
) STRICT;

CREATE TABLE crops (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,   -- 'zucchini', 'maize', 'cilantro'
  scientific_name TEXT,
  family          TEXT                    -- for rotation: 'Cucurbitaceae', ...
) STRICT;

CREATE TABLE varieties (
  id                      INTEGER PRIMARY KEY,
  crop_id                 INTEGER NOT NULL REFERENCES crops(id),
  name                    TEXT NOT NULL,  -- 'President F1', 'Criollo de Alexander (MIDA)'
  seller                  TEXT,
  packet_days_to_maturity INTEGER CHECK (packet_days_to_maturity > 0),  -- goal 3: packet vs actual
  notes                   TEXT,
  UNIQUE (crop_id, name)
) STRICT;

CREATE TABLE inputs (                     -- things applied: biochar mix, bone ash, Great White …
  id      INTEGER PRIMARY KEY,
  name    TEXT NOT NULL UNIQUE,
  kind    TEXT CHECK (kind IN ('fertilizer','amendment','inoculant','biocontrol','mulch','water','other')),
  recipe  TEXT,                           -- e.g. 'Great White : bentonite 1:3.6'
  notes   TEXT
) STRICT;

CREATE TABLE trials (                     -- goals 4 and 7
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  question    TEXT,              -- 'Which zucchini yields most per m² in the wet season?'
  design      TEXT CHECK (design IN ('observation','replicated','tricot','paired_control')),
  start_date  TEXT CHECK (start_date IS date(start_date)),
  notes       TEXT
) STRICT;

-- ── Goal 1: core log ────────────────────────────────────────────────

CREATE TABLE plantings (
  id              INTEGER PRIMARY KEY,
  crop_id         INTEGER NOT NULL REFERENCES crops(id),
  variety_id      INTEGER REFERENCES varieties(id),   -- optional: variety may be unknown
  bed_id          INTEGER REFERENCES beds(id),
  location_detail TEXT,                   -- free text if finer than the bed
  method          TEXT CHECK (method IN ('direct_seed','transplant','cutting','tuber','sucker')),
  sow_date        TEXT CHECK (sow_date IS date(sow_date)),
  transplant_date TEXT CHECK (transplant_date IS date(transplant_date) AND transplant_date >= sow_date),
  n_plants        INTEGER CHECK (n_plants > 0),
  area_m2         REAL CHECK (area_m2 > 0),  -- needed for yield per m²
  trial_id        INTEGER REFERENCES trials(id),
  treatment       TEXT,                   -- 'control', 'biochar', or variety label in a variety trial
  replicate       INTEGER CHECK (replicate > 0),
  ended_date      TEXT CHECK (ended_date IS date(ended_date) AND ended_date >= sow_date),
  notes           TEXT,
  CHECK (trial_id IS NOT NULL OR (treatment IS NULL AND replicate IS NULL))
) STRICT;

CREATE TABLE harvests (
  id          INTEGER PRIMARY KEY,
  date        TEXT NOT NULL CHECK (date IS date(date)),
  planting_id INTEGER NOT NULL REFERENCES plantings(id),
  weight_kg   REAL CHECK (weight_kg >= 0),
  count       INTEGER CHECK (count >= 0),
  notes       TEXT,
  CHECK (weight_kg IS NOT NULL OR count IS NOT NULL)
) STRICT;

-- ── Goal 2: inputs applied ──────────────────────────────────────────

CREATE TABLE applications (
  id          INTEGER PRIMARY KEY,
  date        TEXT NOT NULL CHECK (date IS date(date)),
  planting_id INTEGER REFERENCES plantings(id),
  bed_id      INTEGER REFERENCES beds(id),   -- when applied to a bed with no planting
  input_id    INTEGER NOT NULL REFERENCES inputs(id),
  quantity    REAL CHECK (quantity >= 0),
  unit        TEXT,                          -- 'g', 'kg', 'L', 'mL'
  basis       TEXT CHECK (basis IN ('per_plant','per_cluster','per_m2','total')),
  notes       TEXT,
  CHECK (planting_id IS NOT NULL OR bed_id IS NOT NULL),
  CHECK (quantity IS NULL OR unit IS NOT NULL)
) STRICT;

-- ── Goal 4: taste / quality scores (also tricot ranks) ──────────────

CREATE TABLE evaluations (
  id          INTEGER PRIMARY KEY,
  date        TEXT NOT NULL CHECK (date IS date(date)),
  planting_id INTEGER NOT NULL REFERENCES plantings(id),
  trait       TEXT NOT NULL CHECK (trait IN ('taste','texture','appearance','vigor','pest_resistance','disease_resistance','overall')),
  score       INTEGER CHECK (score BETWEEN 1 AND 5),
  rank        INTEGER CHECK (rank > 0),       -- tricot: 1 = best of the set
  evaluator   TEXT,                           -- 'family', 'buyer', … (no personal data)
  notes       TEXT,
  CHECK (score IS NOT NULL OR rank IS NOT NULL)
) STRICT;

-- ── Goals 5 and 10: where the harvest went ─────────────────────────

CREATE TABLE dispositions (
  id              INTEGER PRIMARY KEY,
  date            TEXT NOT NULL CHECK (date IS date(date)),
  crop_id         INTEGER NOT NULL REFERENCES crops(id),
  planting_id     INTEGER REFERENCES plantings(id),  -- if known
  kind            TEXT NOT NULL CHECK (kind IN ('sold','family','given','unsold','spoiled','seed')),
  quantity        REAL NOT NULL CHECK (quantity >= 0),
  unit            TEXT NOT NULL CHECK (unit IN ('kg','count','bunch')),
  price_total_usd REAL CHECK (price_total_usd >= 0),
  channel         TEXT,                               -- 'neighbours', 'market', 'restaurant', …
  notes           TEXT,
  CHECK (kind = 'sold' OR price_total_usd IS NULL)
) STRICT;

CREATE TABLE family_needs (              -- goal 10 target
  id          INTEGER PRIMARY KEY,
  crop_id     INTEGER NOT NULL UNIQUE REFERENCES crops(id),
  kg_per_week REAL NOT NULL CHECK (kg_per_week > 0),
  notes       TEXT
) STRICT;

-- ── Goal 6: pests, diseases, phenology ──────────────────────────────

CREATE TABLE observations (
  id            INTEGER PRIMARY KEY,
  date          TEXT NOT NULL CHECK (date IS date(date)),
  planting_id   INTEGER REFERENCES plantings(id),
  bed_id        INTEGER REFERENCES beds(id),
  kind          TEXT NOT NULL CHECK (kind IN ('pest','disease','deficiency','phenology','weather_damage','other')),
  subject       TEXT NOT NULL,             -- 'powdery mildew', 'first female flower'
  severity      INTEGER CHECK (severity BETWEEN 0 AND 5),
  incidence_pct REAL CHECK (incidence_pct BETWEEN 0 AND 100),  -- % of plants affected
  action        TEXT,                      -- what was done
  notes         TEXT,
  CHECK (planting_id IS NOT NULL OR bed_id IS NOT NULL)
) STRICT;

-- ── Goal 8: soil ───────────────────────────────────────────────────

CREATE TABLE soil_tests (
  id              INTEGER PRIMARY KEY,
  date            TEXT NOT NULL CHECK (date IS date(date)),
  bed_id          INTEGER REFERENCES beds(id),
  location_detail TEXT,
  parameter       TEXT NOT NULL CHECK (parameter IN ('ph','organic_matter','n','p','k','ca','mg','ec','other')),
  value           REAL NOT NULL,
  value_high      REAL,                    -- for ranges like pH 6.6–6.7 (value = low end)
  unit            TEXT,                    -- NULL for pH
  method          TEXT,                    -- 'pH strip', 'meter', lab name
  notes           TEXT,
  CHECK (value_high IS NULL OR value_high >= value),
  CHECK (bed_id IS NOT NULL OR location_detail IS NOT NULL)
) STRICT;

-- ── Goal 9: weather ────────────────────────────────────────────────

CREATE TABLE weather (
  id         INTEGER PRIMARY KEY,
  date       TEXT NOT NULL UNIQUE CHECK (date IS date(date)),
  rain_mm    REAL CHECK (rain_mm >= 0),
  temp_min_c REAL,
  temp_max_c REAL,
  rh_pct     REAL CHECK (rh_pct BETWEEN 0 AND 100),
  source     TEXT,                         -- 'rain gauge', 'station'
  notes      TEXT,
  CHECK (temp_min_c IS NULL OR temp_max_c IS NULL OR temp_max_c >= temp_min_c)
) STRICT;

-- ── Indexes for the common lookups ─────────────────────────────────

CREATE INDEX harvests_planting     ON harvests(planting_id, date);
CREATE INDEX applications_planting ON applications(planting_id, date);
CREATE INDEX observations_planting ON observations(planting_id, date);
CREATE INDEX evaluations_planting  ON evaluations(planting_id);
CREATE INDEX plantings_variety     ON plantings(variety_id);

-- ── Goal 3 + 4 answers, computed (never stored) ────────────────────

CREATE VIEW planting_summary AS
SELECT p.id AS planting_id, c.name AS crop, v.name AS variety, b.name AS bed,
       p.sow_date,
       MIN(h.date) AS first_harvest, MAX(h.date) AS last_harvest,
       CAST(julianday(MIN(h.date)) - julianday(p.sow_date) AS INTEGER) AS days_to_first_harvest,
       v.packet_days_to_maturity,
       CAST(julianday(MAX(h.date)) - julianday(MIN(h.date)) AS INTEGER) AS harvest_window_days,
       ROUND(SUM(h.weight_kg), 3) AS total_kg,
       ROUND(SUM(h.weight_kg) / p.area_m2, 3) AS kg_per_m2,
       ROUND(SUM(h.weight_kg) / p.n_plants, 3) AS kg_per_plant,
       p.trial_id, p.treatment, p.replicate
FROM plantings p
JOIN crops c     ON c.id = p.crop_id
LEFT JOIN varieties v ON v.id = p.variety_id
LEFT JOIN beds b ON b.id = p.bed_id
LEFT JOIN harvests h ON h.planting_id = p.id
GROUP BY p.id;
