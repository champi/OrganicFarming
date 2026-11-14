"""Schema migrations: ordering, atomicity, bookkeeping, tamper detection."""
import unittest

from helpers import farmdb  # noqa: F401
from farmdb import db, migrations as mig
from farmdb.errors import FarmError

NOW = "2026-11-14T12:00:00Z"

M1 = {"001_beds.sql": "CREATE TABLE bed (id INTEGER PRIMARY KEY, name TEXT NOT NULL) STRICT;"}
M2 = {**M1, "002_plantings.sql": """
CREATE TABLE planting (id INTEGER PRIMARY KEY,
    bed_id INTEGER NOT NULL REFERENCES bed(id), crop TEXT NOT NULL) STRICT;
CREATE TRIGGER planting_crop_lower BEFORE INSERT ON planting
WHEN NEW.crop <> lower(NEW.crop)
BEGIN SELECT RAISE(ABORT, 'crop must be lowercase'); END;
"""}


def tables(conn):
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


class Apply(unittest.TestCase):
    def test_applies_in_numeric_order_and_records_them(self):
        conn = db.load("")
        files = {"010_late.sql": "CREATE TABLE late (id INTEGER PRIMARY KEY, "
                                 "e INTEGER REFERENCES early(id)) STRICT;",
                 "002_early.sql": "CREATE TABLE early (id INTEGER PRIMARY KEY) STRICT;"}
        applied = mig.apply_pending(conn, files, NOW)
        self.assertEqual(applied, ["002_early.sql", "010_late.sql"])
        rows = conn.execute("SELECT name, applied_at FROM schema_migrations ORDER BY name").fetchall()
        self.assertEqual(rows, [("002_early.sql", NOW), ("010_late.sql", NOW)])
        self.assertEqual(db.check(conn), [])

    def test_rerun_applies_nothing(self):
        conn = db.load("")
        mig.apply_pending(conn, M2, NOW)
        self.assertEqual(mig.apply_pending(conn, M2, NOW), [])

    def test_only_new_migrations_are_applied(self):
        conn = db.load("")
        mig.apply_pending(conn, M1, NOW)
        self.assertEqual(mig.apply_pending(conn, M2, NOW), ["002_plantings.sql"])
        self.assertEqual(tables(conn), {"bed", "planting", "schema_migrations"})

    def test_triggers_with_inner_semicolons_work(self):
        conn = db.load("")
        mig.apply_pending(conn, M2, NOW)
        conn.execute("INSERT INTO bed VALUES (1, 'A')")
        with self.assertRaises(Exception):
            conn.execute("INSERT INTO planting VALUES (1, 1, 'Corn')")

    def test_bookkeeping_survives_dump_and_reload(self):
        conn = db.load("")
        mig.apply_pending(conn, M2, NOW)
        reloaded = db.load(db.dump(conn))
        self.assertEqual(mig.pending(reloaded, M2), [])
        self.assertEqual(mig.problems(reloaded, M2), [])

    def test_foreign_keys_are_on_after_applying(self):
        conn = db.load("")
        mig.apply_pending(conn, M2, NOW)
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)


class Atomicity(unittest.TestCase):
    def assertRejectedWithoutChange(self, conn, files):
        before = db.dump(conn)
        with self.assertRaises(FarmError) as ctx:
            mig.apply_pending(conn, files, NOW)
        self.assertEqual(db.dump(conn), before)
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertFalse(conn.in_transaction)
        return str(ctx.exception)

    def test_failing_statement_rolls_back_whole_migration(self):
        conn = db.load("")
        msg = self.assertRejectedWithoutChange(conn, {
            "001_x.sql": "CREATE TABLE ok (id INTEGER PRIMARY KEY) STRICT; NOT VALID SQL;"})
        self.assertIn("001_x.sql", msg)

    def test_failure_in_second_keeps_first_rolled_back_too(self):
        # A run is all-or-nothing, so the saved database never sits half-migrated.
        conn = db.load("")
        self.assertRejectedWithoutChange(conn, {
            **M1, "002_bad.sql": "CREATE TABLE broken (;"})
        self.assertEqual(tables(conn), set())

    def test_non_strict_table_is_rejected(self):
        conn = db.load("")
        msg = self.assertRejectedWithoutChange(conn, {
            "001_loose.sql": "CREATE TABLE loose (id INTEGER PRIMARY KEY);"})
        self.assertIn("STRICT", msg)

    def test_table_without_integer_primary_key_is_rejected(self):
        conn = db.load("")
        self.assertRejectedWithoutChange(conn, {
            "001_nopk.sql": "CREATE TABLE nopk (name TEXT) STRICT;"})

    def test_migration_leaving_dangling_foreign_keys_is_rejected(self):
        conn = db.load("")
        mig.apply_pending(conn, M2, NOW)
        conn.execute("INSERT INTO bed VALUES (1, 'A')")
        conn.execute("INSERT INTO planting VALUES (1, 1, 'corn')")
        msg = self.assertRejectedWithoutChange(conn, {**M2, "003_drop.sql": "DELETE FROM bed;"})
        self.assertIn("foreign key", msg)

    def test_table_rebuild_with_foreign_keys_is_allowed(self):
        # SQLite's documented 12-step ALTER: rebuild a referenced table.
        conn = db.load("")
        mig.apply_pending(conn, M2, NOW)
        conn.execute("INSERT INTO bed VALUES (1, 'A')")
        conn.execute("INSERT INTO planting VALUES (1, 1, 'corn')")
        mig.apply_pending(conn, {**M2, "003_rebuild_bed.sql": """
            CREATE TABLE bed_new (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                                  area_m2 REAL) STRICT;
            INSERT INTO bed_new (id, name) SELECT id, name FROM bed;
            DROP TABLE bed;
            ALTER TABLE bed_new RENAME TO bed;
        """}, NOW)
        self.assertEqual(db.check(conn), [])
        self.assertEqual(conn.execute("SELECT count(*) FROM planting").fetchone()[0], 1)

    def test_transaction_control_and_pragmas_are_rejected(self):
        for sql in ["COMMIT;", "BEGIN; CREATE TABLE t (id INTEGER PRIMARY KEY) STRICT; COMMIT;",
                    "PRAGMA foreign_keys = OFF;", "SAVEPOINT s;", "ANALYZE;",
                    "ATTACH DATABASE ':memory:' AS other;"]:
            with self.subTest(sql=sql):
                self.assertRejectedWithoutChange(db.load(""), {"001_x.sql": sql})

    def test_migration_cannot_forge_bookkeeping(self):
        conn = db.load("")
        self.assertRejectedWithoutChange(conn, {
            "001_x.sql": "INSERT INTO schema_migrations VALUES ('999_fake.sql', 'x', 'y');"})

    def test_empty_migration_is_rejected(self):
        self.assertRejectedWithoutChange(db.load(""), {"001_x.sql": "-- nothing yet\n"})


class Names(unittest.TestCase):
    def test_bad_file_names_are_rejected(self):
        for name in ["1_x.sql", "001-x.sql", "001_X.sql", "001_x.txt", "x_001.sql", "001_.sql"]:
            with self.subTest(name=name):
                with self.assertRaises(FarmError):
                    mig.apply_pending(db.load(""), {name: "SELECT 1;"}, NOW)

    def test_duplicate_numbers_are_rejected(self):
        with self.assertRaises(FarmError):
            mig.apply_pending(db.load(""), {
                "001_a.sql": "CREATE TABLE a (id INTEGER PRIMARY KEY) STRICT;",
                "001_b.sql": "CREATE TABLE b (id INTEGER PRIMARY KEY) STRICT;"}, NOW)


class Problems(unittest.TestCase):
    def setUp(self):
        self.conn = db.load("")
        mig.apply_pending(self.conn, M2, NOW)

    def test_in_sync_has_no_problems(self):
        self.assertEqual(mig.problems(self.conn, M2), [])

    def test_pending_migration_is_not_a_problem(self):
        files = {**M2, "003_more.sql": "CREATE TABLE more (id INTEGER PRIMARY KEY) STRICT;"}
        self.assertEqual(mig.problems(self.conn, files), [])
        self.assertEqual(mig.pending(self.conn, files), ["003_more.sql"])

    def test_edited_applied_migration_is_reported(self):
        files = {**M2, "001_beds.sql": M1["001_beds.sql"] + "\n-- edited"}
        problems = mig.problems(self.conn, files)
        self.assertTrue(any("001_beds.sql" in p and "changed" in p for p in problems), problems)

    def test_deleted_applied_migration_is_reported(self):
        files = {"002_plantings.sql": M2["002_plantings.sql"]}
        problems = mig.problems(self.conn, files)
        self.assertTrue(any("001_beds.sql" in p and "missing" in p for p in problems), problems)

    def test_out_of_order_new_migration_is_reported_and_not_applied(self):
        files = {**M2, "001b_x.sql": "x"}  # bad name anyway
        self.assertTrue(mig.problems(self.conn, files))
        files = {**M2, "000_early.sql": "CREATE TABLE early (id INTEGER PRIMARY KEY) STRICT;"}
        problems = mig.problems(self.conn, files)
        self.assertTrue(any("000_early.sql" in p and "older" in p for p in problems), problems)
        with self.assertRaises(FarmError):
            mig.apply_pending(self.conn, files, NOW)

    def test_database_without_bookkeeping_has_everything_pending(self):
        self.assertEqual(mig.pending(db.load(""), M2), ["001_beds.sql", "002_plantings.sql"])
        self.assertEqual(mig.problems(db.load(""), M2), [])


if __name__ == "__main__":
    unittest.main()
