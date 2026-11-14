-- Corn (and other crops) planted in clusters: number of clusters per planting.
ALTER TABLE plantings ADD COLUMN n_clusters INTEGER CHECK (n_clusters > 0);
