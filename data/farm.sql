BEGIN TRANSACTION;
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
INSERT INTO "applications" VALUES(1,'2026-09-04',5,NULL,1,NULL,NULL,NULL,'at sowing');
INSERT INTO "applications" VALUES(2,'2026-09-20',6,NULL,1,NULL,NULL,NULL,'at sowing');
INSERT INTO "applications" VALUES(3,'2026-10-01',7,NULL,1,NULL,NULL,NULL,'at sowing');
INSERT INTO "applications" VALUES(4,'2026-10-02',8,NULL,1,NULL,NULL,NULL,'at sowing');
INSERT INTO "applications" VALUES(5,'2026-10-12',9,NULL,1,NULL,NULL,NULL,'at sowing');
INSERT INTO "applications" VALUES(6,'2026-10-12',10,NULL,1,NULL,NULL,NULL,'at sowing');
INSERT INTO "applications" VALUES(7,'2026-10-12',11,NULL,1,NULL,NULL,NULL,'at sowing');
INSERT INTO "applications" VALUES(8,'2026-10-12',9,NULL,2,NULL,NULL,NULL,'at sowing');
INSERT INTO "applications" VALUES(9,'2026-10-12',10,NULL,2,NULL,NULL,NULL,'at sowing');
INSERT INTO "applications" VALUES(10,'2026-10-12',11,NULL,2,NULL,NULL,NULL,'at sowing');
INSERT INTO "applications" VALUES(11,'2026-10-12',1,NULL,2,NULL,NULL,NULL,NULL);
INSERT INTO "applications" VALUES(12,'2026-10-09',5,NULL,3,NULL,NULL,NULL,NULL);
INSERT INTO "applications" VALUES(13,'2026-09-16',12,NULL,1,NULL,NULL,NULL,'at sowing');
INSERT INTO "applications" VALUES(14,'2026-10-05',12,NULL,2,NULL,NULL,NULL,'trial sheet: biochar charged with aged urine + 5 g/L Epsom');
INSERT INTO "applications" VALUES(15,'2026-10-12',12,NULL,4,NULL,NULL,NULL,'from xlsx; trial log row for this date is empty');
INSERT INTO "applications" VALUES(16,'2026-10-18',12,NULL,7,150.0,'mL','per_plant','xlsx has "Fresh U" on 2026-10-19');
INSERT INTO "applications" VALUES(17,'2026-10-24',12,NULL,9,30.0,'g','per_plant','15 g bone ash + 15 g vermicast, ring 20-25 cm');
INSERT INTO "applications" VALUES(18,'2026-10-27',12,NULL,7,150.0,'mL','per_plant',NULL);
INSERT INTO "applications" VALUES(19,'2026-11-01',12,NULL,10,5.0,'g','per_plant','approximate date (around Nov 1; exact date not recorded)');
INSERT INTO "applications" VALUES(20,'2026-11-08',12,NULL,5,NULL,NULL,NULL,'~200-250 mL per plant, diluted ~1:5');
INSERT INTO "applications" VALUES(21,'2026-11-14',12,NULL,6,200.0,'mL','per_plant',NULL);
INSERT INTO "applications" VALUES(22,'2026-11-14',12,NULL,10,5.0,'g','per_plant',NULL);
INSERT INTO "applications" VALUES(23,'2026-11-14',13,NULL,10,15.0,'g','per_plant','first of 3 x 15 g SOP');
INSERT INTO "applications" VALUES(24,'2026-11-14',13,NULL,8,300.0,'mL','per_plant',NULL);
INSERT INTO "applications" VALUES(25,'2026-11-14',14,NULL,10,7.0,'g','total','whole bed');
INSERT INTO "applications" VALUES(26,'2026-11-14',14,NULL,8,250.0,'mL','total','whole bed');
CREATE TABLE beds (                       -- where things grow
  id        INTEGER PRIMARY KEY,
  name      TEXT NOT NULL UNIQUE,         -- e.g. 'Raised bed baru 2', 'Entrance mounds row 1-4'
  site      TEXT CHECK (site IN ('farm','rented_house')),
  kind      TEXT CHECK (kind IN ('raised_bed','mound_row','field','tunnel','pot','other')),
  area_m2   REAL CHECK (area_m2 > 0),
  notes     TEXT
) STRICT;
INSERT INTO "beds" VALUES(1,'Land entrance mounds row 1-4','farm','mound_row',NULL,NULL);
INSERT INTO "beds" VALUES(2,'Land entrance mounds row 5-7','farm','mound_row',NULL,NULL);
INSERT INTO "beds" VALUES(3,'Land entrance after mounds row 1-4','farm','field',NULL,NULL);
INSERT INTO "beds" VALUES(4,'Land 2 (27 rows)','farm','field',NULL,NULL);
INSERT INTO "beds" VALUES(5,'Land 1 (~14 rows after row 4 after mounds)','farm','field',NULL,NULL);
INSERT INTO "beds" VALUES(6,'Land 2 near big pine','farm','field',NULL,NULL);
INSERT INTO "beds" VALUES(7,'Rented house raised garden bed','rented_house','raised_bed',NULL,'xlsx tab "Plants baru 2"; "cama jardin elevada"');
INSERT INTO "beds" VALUES(8,'Sweet potato + strawberry bed','rented_house','raised_bed',NULL,'2 x 0.5 m, almost pure sand');
CREATE TABLE crops (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,   -- 'zucchini', 'maize', 'cilantro'
  scientific_name TEXT,
  family          TEXT                    -- for rotation: 'Cucurbitaceae', ...
) STRICT;
INSERT INTO "crops" VALUES(1,'cilantro','Coriandrum sativum',NULL);
INSERT INTO "crops" VALUES(2,'otoe','Xanthosoma sagittifolium',NULL);
INSERT INTO "crops" VALUES(3,'sweet potato','Ipomoea batatas',NULL);
INSERT INTO "crops" VALUES(4,'potato','Solanum tuberosum',NULL);
INSERT INTO "crops" VALUES(5,'maize','Zea mays',NULL);
INSERT INTO "crops" VALUES(6,'cherry tomato','Solanum lycopersicum',NULL);
INSERT INTO "crops" VALUES(7,'lima bean','Phaseolus lunatus',NULL);
INSERT INTO "crops" VALUES(8,'common bean','Phaseolus vulgaris',NULL);
INSERT INTO "crops" VALUES(9,'zucchini','Cucurbita pepo',NULL);
INSERT INTO "crops" VALUES(10,'pumpkin',NULL,NULL);
INSERT INTO "crops" VALUES(11,'strawberry',NULL,NULL);
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
CREATE TABLE family_needs (              -- goal 10 target
  id          INTEGER PRIMARY KEY,
  crop_id     INTEGER NOT NULL UNIQUE REFERENCES crops(id),
  kg_per_week REAL NOT NULL CHECK (kg_per_week > 0),
  notes       TEXT
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
INSERT INTO "harvests" VALUES(1,'2026-11-09',12,0.975,3,'2 x 21 cm (~275 g), 1 x 28 cm (425 g); 5 days after pollination');
INSERT INTO "harvests" VALUES(2,'2026-11-13',12,0.771,3,NULL);
CREATE TABLE inputs (                     -- things applied: biochar mix, bone ash, Great White …
  id      INTEGER PRIMARY KEY,
  name    TEXT NOT NULL UNIQUE,
  kind    TEXT CHECK (kind IN ('fertilizer','amendment','inoculant','biocontrol','mulch','water','other')),
  recipe  TEXT,                           -- e.g. 'Great White : bentonite 1:3.6'
  notes   TEXT
) STRICT;
INSERT INTO "inputs" VALUES(1,'Great White + bentonite','inoculant','Great White : bentonite 1:3.6',NULL);
INSERT INTO "inputs" VALUES(2,'Biochar + vermicast','amendment',NULL,NULL);
INSERT INTO "inputs" VALUES(3,'Biochar + vermicast + urine (5 g/L Epsom)','amendment',NULL,NULL);
INSERT INTO "inputs" VALUES(4,'Urine, aged + Epsom 5 g/L','fertilizer',NULL,NULL);
INSERT INTO "inputs" VALUES(5,'Urine, aged','fertilizer',NULL,NULL);
INSERT INTO "inputs" VALUES(6,'Urine, fresh','fertilizer',NULL,NULL);
INSERT INTO "inputs" VALUES(7,'Urine, fresh + white vinegar','fertilizer',NULL,NULL);
INSERT INTO "inputs" VALUES(8,'Urine','fertilizer','type not recorded',NULL);
INSERT INTO "inputs" VALUES(9,'Bone ash + vermicast 1:1','fertilizer','raw fine-ground bone ash : vermicast 1:1 by weight',NULL);
INSERT INTO "inputs" VALUES(10,'Potassium sulfate (SOP)','fertilizer','0-0-50',NULL);
INSERT INTO "inputs" VALUES(11,'Seedling mix','amendment','All sieved: 35% pine needle leaf mold (neighbour pine forest, contains natural biochar), 35% native soil (entrance mounds line 7, near waterway channel), 20% vermicast, 10% urine-charged biochar',NULL);
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
INSERT INTO "observations" VALUES(1,'2026-10-26',12,NULL,'phenology','flower buds forming (male and female)',NULL,100.0,NULL,'small, none open');
INSERT INTO "observations" VALUES(2,'2026-10-31',12,NULL,'phenology','first male flowers open',NULL,50.0,NULL,'2 of 4 plants');
INSERT INTO "observations" VALUES(3,'2026-11-02',12,NULL,'phenology','first female flowers open',NULL,75.0,NULL,'approximate (~Nov 2-4); 3 of 4 plants, 1 each');
INSERT INTO "observations" VALUES(4,'2026-11-04',12,NULL,'phenology','hand-pollinated 3 female flowers',NULL,NULL,NULL,NULL);
INSERT INTO "observations" VALUES(5,'2026-11-08',12,NULL,'other','cat damage to plant 4',NULL,25.0,NULL,'female flowers and baby fruit knocked off; tip and main stem slightly damaged. Hand-pollinated 3 new female flowers');
INSERT INTO "observations" VALUES(6,'2026-11-13',12,NULL,'phenology','plant 4 opens only male flowers',NULL,NULL,NULL,'used to hand-pollinate the other 3, which have only female flowers');
INSERT INTO "observations" VALUES(7,'2026-11-14',13,NULL,'phenology','first male flowers opening',NULL,NULL,NULL,NULL);
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
  notes           TEXT, n_clusters INTEGER CHECK (n_clusters > 0),
  CHECK (trial_id IS NOT NULL OR (treatment IS NULL AND replicate IS NULL))
) STRICT;
INSERT INTO "plantings" VALUES(1,1,1,1,NULL,NULL,'2026-08-29',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "plantings" VALUES(2,2,NULL,2,NULL,NULL,'2026-09-01',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'xlsx row "otoe camote papa"',NULL);
INSERT INTO "plantings" VALUES(3,3,NULL,2,NULL,NULL,'2026-09-01',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'xlsx row "otoe camote papa"',NULL);
INSERT INTO "plantings" VALUES(4,4,NULL,2,NULL,NULL,'2026-09-01',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'xlsx row "otoe camote papa"',NULL);
INSERT INTO "plantings" VALUES(5,5,2,3,NULL,NULL,'2026-09-04',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'Great White:bentonite powder:seed 1:34.75',NULL);
INSERT INTO "plantings" VALUES(6,6,NULL,2,NULL,'transplant','2026-09-20',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'xlsx: "tomate cherry transplant"; 2026-09-20 recorded as sowing date',NULL);
INSERT INTO "plantings" VALUES(7,5,2,4,NULL,NULL,'2026-10-01',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'xlsx "Nb plants" = 434 (dose log counts these as clusters)',NULL);
INSERT INTO "plantings" VALUES(8,5,2,5,NULL,NULL,'2026-10-02',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'xlsx "Nb plants" = 80 (dose log counts these as clusters)',NULL);
INSERT INTO "plantings" VALUES(9,7,NULL,3,NULL,NULL,'2026-10-12',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'xlsx row "Frijol Lima + Frijol Conejo"',NULL);
INSERT INTO "plantings" VALUES(10,8,3,3,NULL,NULL,'2026-10-12',NULL,NULL,NULL,NULL,NULL,NULL,NULL,'xlsx row "Frijol Lima + Frijol Conejo"',NULL);
INSERT INTO "plantings" VALUES(11,9,4,6,NULL,NULL,'2026-10-12',NULL,9,NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "plantings" VALUES(12,9,4,7,NULL,'direct_seed','2026-09-16',NULL,4,NULL,NULL,NULL,NULL,NULL,'Trial: zucchini-trial-2026-president-f1.md; ~1 m2 per plant',NULL);
INSERT INTO "plantings" VALUES(13,10,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'Rented house; sow date not recorded (garden-input-log-2026.md)',NULL);
INSERT INTO "plantings" VALUES(14,3,NULL,8,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'4-6 plants, with strawberries',NULL);
CREATE TABLE schema_migrations (
    name TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    applied_at TEXT NOT NULL
) STRICT, WITHOUT ROWID;
INSERT INTO "schema_migrations" VALUES('001_core.sql','9d8300e24963eb257c95f677af22a546bc6d6b1b400720458175bea17669a1f0','2026-11-14T18:47:32Z');
INSERT INTO "schema_migrations" VALUES('002_planting_clusters.sql','5b42068a9e290f9c9ef7edbbaca7191f7e97fe482debd96b7e1a637e4483afd0','2026-11-14T19:19:50Z');
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
INSERT INTO "soil_tests" VALUES(1,'2026-09-05',7,NULL,'ph',6.9,NULL,NULL,NULL,NULL);
INSERT INTO "soil_tests" VALUES(2,'2026-09-05',NULL,'Farm: near entrance mounds line 7, near waterway channel','ph',6.6,6.7,NULL,NULL,NULL);
CREATE TABLE trials (                     -- goals 4 and 7
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  question    TEXT,              -- 'Which zucchini yields most per m² in the wet season?'
  design      TEXT CHECK (design IN ('observation','replicated','tricot','paired_control')),
  start_date  TEXT CHECK (start_date IS date(start_date)),
  notes       TEXT
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
INSERT INTO "varieties" VALUES(1,1,'de Ramon',NULL,NULL,NULL);
INSERT INTO "varieties" VALUES(2,5,'Criollo de Alexander','MIDA',NULL,NULL);
INSERT INTO "varieties" VALUES(3,8,'Conejo',NULL,NULL,NULL);
INSERT INTO "varieties" VALUES(4,9,'President F1',NULL,NULL,NULL);
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
CREATE INDEX harvests_planting     ON harvests(planting_id, date);
CREATE INDEX applications_planting ON applications(planting_id, date);
CREATE INDEX observations_planting ON observations(planting_id, date);
CREATE INDEX evaluations_planting  ON evaluations(planting_id);
CREATE INDEX plantings_variety     ON plantings(variety_id);
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
COMMIT;
