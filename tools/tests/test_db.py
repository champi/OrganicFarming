"""Core database tests: dump/load fidelity, integrity checks, guarded writes."""
import sqlite3
import unittest

from helpers import farmdb  # noqa: F401  (sets sys.path)
from farmdb import db
from farmdb.errors import FarmError


SCHEMA = """
CREATE TABLE bed (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE) STRICT;
CREATE TABLE planting (
    id INTEGER PRIMARY KEY,
    bed_id INTEGER NOT NULL REFERENCES bed(id),
    crop TEXT NOT NULL,
    n_plants INTEGER CHECK (n_plants > 0)
) STRICT;
"""


def fresh(sql=SCHEMA):
    return db.load(sql)


class LoadDumpRoundTrip(unittest.TestCase):
    def assertRoundTrips(self, conn):
        first = db.dump(conn)
        second = db.dump(db.load(first))
        self.assertEqual(first, second)
        return first

    def test_empty_database_round_trips(self):
        self.assertRoundTrips(db.load(""))

    def test_awkward_text_values_survive(self):
        conn = fresh()
        tricky = ["O'Neil", 'say "hi"', "a,b;c", "line1\nline2", "tab\there",
                  "accents éñü 🌱", "", "--not a comment", "NULL"]
        for i, value in enumerate(tricky, start=1):
            conn.execute("INSERT INTO bed VALUES (?, ?)", (i, value))
        reloaded = db.load(self.assertRoundTrips(conn))
        got = [r[0] for r in reloaded.execute("SELECT name FROM bed ORDER BY id")]
        self.assertEqual(got, tricky)

    def test_real_numbers_keep_full_precision(self):
        conn = db.load("CREATE TABLE m (id INTEGER PRIMARY KEY, v REAL) STRICT;")
        values = [0.1 + 0.2, 6.7, 1e300, -0.0, 1 / 3]
        conn.executemany("INSERT INTO m(v) VALUES (?)", [(v,) for v in values])
        reloaded = db.load(self.assertRoundTrips(conn))
        got = [r[0] for r in reloaded.execute("SELECT v FROM m ORDER BY id")]
        self.assertEqual(got, values)

    def test_null_and_blob_survive(self):
        conn = db.load("CREATE TABLE x (id INTEGER PRIMARY KEY, t TEXT, b BLOB) STRICT;")
        conn.execute("INSERT INTO x VALUES (1, NULL, ?)", (b"\x00\xff\n",))
        reloaded = db.load(self.assertRoundTrips(conn))
        self.assertEqual(reloaded.execute("SELECT t, b FROM x").fetchone(),
                         (None, b"\x00\xff\n"))

    def test_autoincrement_counter_survives(self):
        conn = db.load("CREATE TABLE a (id INTEGER PRIMARY KEY AUTOINCREMENT, n TEXT) STRICT;")
        conn.execute("INSERT INTO a(n) VALUES ('x'), ('y')")
        conn.execute("DELETE FROM a WHERE id = 2")
        reloaded = db.load(self.assertRoundTrips(conn))
        reloaded.execute("INSERT INTO a(n) VALUES ('z')")
        self.assertEqual(reloaded.execute("SELECT max(id) FROM a").fetchone()[0], 3)

    def test_triggers_do_not_fire_while_loading(self):
        conn = db.load("""
            CREATE TABLE a (id INTEGER PRIMARY KEY, n TEXT) STRICT;
            CREATE TABLE audit (id INTEGER PRIMARY KEY, a_id INTEGER) STRICT;
            CREATE TRIGGER t AFTER INSERT ON a BEGIN
                INSERT INTO audit(a_id) VALUES (NEW.id);
            END;
        """)
        conn.execute("INSERT INTO a VALUES (1, 'x')")
        reloaded = db.load(self.assertRoundTrips(conn))
        self.assertEqual(reloaded.execute("SELECT count(*) FROM audit").fetchone()[0], 1)

    def test_tables_referencing_later_tables_load(self):
        # 'a_child' sorts before 'z_parent' in the dump; loading must not trip FKs.
        conn = db.load("""
            CREATE TABLE z_parent (id INTEGER PRIMARY KEY) STRICT;
            CREATE TABLE a_child (id INTEGER PRIMARY KEY,
                p INTEGER NOT NULL REFERENCES z_parent(id)) STRICT;
        """)
        conn.execute("INSERT INTO z_parent VALUES (1)")
        conn.execute("INSERT INTO a_child VALUES (1, 1)")
        self.assertRoundTrips(conn)

    def test_value_formatting_is_fixed_and_independent_of_sqlite_version(self):
        # SQLite's quote() changed float formatting between 3.45 and 3.53; the dump
        # must not change when the system SQLite does.
        conn = db.load("CREATE TABLE m (id INTEGER PRIMARY KEY, r REAL, t TEXT, b BLOB, n TEXT) STRICT;")
        conn.execute("INSERT INTO m VALUES (1, ?, ?, ?, NULL)", (1 / 3, "O'Neil", b"\x00\xff"))
        conn.execute("INSERT INTO m VALUES (2, 6.0, '', x'', 'x')")
        lines = db.dump(conn).splitlines()
        self.assertIn("INSERT INTO \"m\" VALUES(1,0.3333333333333333,'O''Neil',X'00FF',NULL);", lines)
        self.assertIn("INSERT INTO \"m\" VALUES(2,6.0,'',X'','x');", lines)

    def test_infinite_reals_round_trip(self):
        conn = db.load("CREATE TABLE m (id INTEGER PRIMARY KEY, v REAL) STRICT;")
        conn.executemany("INSERT INTO m(v) VALUES (?)", [(float("inf"),), (float("-inf"),)])
        reloaded = db.load(self.assertRoundTrips(conn))
        self.assertEqual([r[0] for r in reloaded.execute("SELECT v FROM m ORDER BY id")],
                         [float("inf"), float("-inf")])

    def test_nul_character_in_text_is_refused_not_truncated(self):
        conn = db.load("CREATE TABLE m (id INTEGER PRIMARY KEY, t TEXT) STRICT;")
        conn.execute("INSERT INTO m VALUES (1, ?)", ("a\x00b",))
        with self.assertRaises(FarmError):
            db.dump(conn)

    def test_rows_are_dumped_in_key_order(self):
        conn = db.load("CREATE TABLE a (id INTEGER PRIMARY KEY, n TEXT) STRICT;"
                       "CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT) STRICT, WITHOUT ROWID;")
        conn.executemany("INSERT INTO a VALUES (?, 'x')", [(3,), (1,), (2,)])
        conn.executemany("INSERT INTO kv VALUES (?, 'v')", [("c",), ("a",), ("b",)])
        text = db.dump(conn)
        self.assertLess(text.index("VALUES(1,"), text.index("VALUES(2,"))
        self.assertLess(text.index("VALUES(2,"), text.index("VALUES(3,"))
        self.assertLess(text.index("VALUES('a'"), text.index("VALUES('b'"))

    def test_row_order_follows_the_key_even_when_it_is_not_the_first_column(self):
        conn = db.load("CREATE TABLE p (name TEXT, id INTEGER PRIMARY KEY) STRICT;")
        conn.executemany("INSERT INTO p VALUES (?, ?)", [("zucchini", 1), ("apple", 2)])
        text = db.dump(conn)
        self.assertLess(text.index("'zucchini'"), text.index("'apple'"))

    def test_generated_columns_are_not_dumped_as_values(self):
        conn = db.load("CREATE TABLE p (id INTEGER PRIMARY KEY, kg REAL, "
                       "g REAL GENERATED ALWAYS AS (kg * 1000) VIRTUAL) STRICT;")
        conn.execute("INSERT INTO p(id, kg) VALUES (1, 2.5)")
        reloaded = db.load(self.assertRoundTrips(conn))
        self.assertEqual(reloaded.execute("SELECT g FROM p").fetchone()[0], 2500.0)

    def test_views_built_on_views_reload(self):
        conn = db.load("CREATE TABLE t (id INTEGER PRIMARY KEY) STRICT;"
                       "CREATE VIEW zz_base AS SELECT id FROM t;"
                       "CREATE VIEW aa_top AS SELECT id FROM zz_base;")
        conn.execute("INSERT INTO t VALUES (1)")
        reloaded = db.load(self.assertRoundTrips(conn))
        self.assertEqual(reloaded.execute("SELECT id FROM aa_top").fetchone()[0], 1)

    def test_dump_ends_with_newline(self):
        self.assertTrue(db.dump(fresh()).endswith("\n"))

    def test_load_rejects_garbage(self):
        with self.assertRaises(FarmError):
            db.load("THIS IS NOT SQL;")


class ForeignKeys(unittest.TestCase):
    def test_loaded_connection_enforces_foreign_keys(self):
        conn = fresh()
        self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO planting VALUES (1, 99, 'corn', 4)")


class Check(unittest.TestCase):
    def test_clean_database_has_no_problems(self):
        conn = fresh()
        conn.execute("INSERT INTO bed VALUES (1, 'A')")
        conn.execute("INSERT INTO planting VALUES (1, 1, 'corn', 4)")
        self.assertEqual(db.check(conn), [])

    def test_dangling_foreign_key_is_reported(self):
        # A dump edited by hand could contain a dangling reference.
        broken = SCHEMA + "INSERT INTO planting VALUES (1, 42, 'corn', 4);"
        problems = db.check(db.load(broken))
        self.assertTrue(any("foreign key" in p for p in problems), problems)

    def test_non_strict_table_is_reported(self):
        problems = db.check(db.load("CREATE TABLE loose (id INTEGER PRIMARY KEY);"))
        self.assertTrue(any("loose" in p and "STRICT" in p for p in problems), problems)

    def test_table_without_explicit_primary_key_is_reported(self):
        # Implicit rowids are renumbered by a dump/load cycle; forbid them.
        problems = db.check(db.load("CREATE TABLE nopk (name TEXT) STRICT;"))
        self.assertTrue(any("nopk" in p and "PRIMARY KEY" in p for p in problems), problems)

    def test_without_rowid_table_is_accepted(self):
        conn = db.load("CREATE TABLE kv (k TEXT PRIMARY KEY, v TEXT) STRICT, WITHOUT ROWID;")
        self.assertEqual(db.check(conn), [])

    def test_virtual_table_is_reported(self):
        problems = db.check(db.load("CREATE VIRTUAL TABLE f USING fts5(body);"))
        self.assertTrue(any("f" in p and "virtual" in p for p in problems), problems)

    def test_text_primary_key_on_rowid_table_is_reported(self):
        # TEXT PRIMARY KEY on a rowid table still has a hidden, renumberable rowid.
        problems = db.check(db.load("CREATE TABLE t (k TEXT PRIMARY KEY) STRICT;"))
        self.assertTrue(any("t" in p and "PRIMARY KEY" in p for p in problems), problems)


class ExecuteWrite(unittest.TestCase):
    def setUp(self):
        self.conn = fresh()
        self.conn.execute("INSERT INTO bed VALUES (1, 'A')")
        self.before = db.dump(self.conn)

    def test_valid_insert_is_applied(self):
        db.execute_write(self.conn, "INSERT INTO planting VALUES (1, 1, 'corn', 4);")
        self.assertEqual(self.conn.execute("SELECT crop FROM planting").fetchone()[0], "corn")

    def test_multiple_statements_are_applied(self):
        db.execute_write(self.conn, """
            INSERT INTO bed VALUES (2, 'B');
            INSERT INTO planting VALUES (1, 2, 'bean', 10);
        """)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM bed").fetchone()[0], 2)

    def test_foreign_key_violation_is_rejected(self):
        with self.assertRaises(FarmError) as ctx:
            db.execute_write(self.conn, "INSERT INTO planting VALUES (1, 99, 'corn', 4);")
        self.assertIn("FOREIGN KEY", str(ctx.exception).upper())

    def test_check_constraint_violation_is_rejected(self):
        with self.assertRaises(FarmError):
            db.execute_write(self.conn, "INSERT INTO planting VALUES (1, 1, 'corn', 0);")

    def test_strict_type_violation_is_rejected(self):
        with self.assertRaises(FarmError):
            db.execute_write(self.conn, "INSERT INTO planting VALUES (1, 1, 'corn', 'many');")

    def test_failure_midway_leaves_no_partial_changes(self):
        with self.assertRaises(FarmError):
            db.execute_write(self.conn, """
                INSERT INTO bed VALUES (2, 'B');
                INSERT INTO planting VALUES (1, 99, 'corn', 4);
            """)
        self.assertEqual(db.dump(self.conn), self.before)

    def test_schema_changes_are_rejected(self):
        for ddl in ["CREATE TABLE sneaky (id INTEGER PRIMARY KEY) STRICT;",
                    "DROP TABLE planting;",
                    "ALTER TABLE bed ADD COLUMN note TEXT;",
                    "CREATE INDEX i ON bed(name);"]:
            with self.subTest(ddl=ddl):
                with self.assertRaises(FarmError) as ctx:
                    db.execute_write(self.conn, ddl)
                self.assertIn("migration", str(ctx.exception).lower())
                self.assertEqual(db.dump(self.conn), self.before)

    def test_transaction_control_in_user_sql_is_rejected(self):
        # A user COMMIT could end our transaction early and defeat rollback.
        for sql in ["COMMIT;", "BEGIN; INSERT INTO bed VALUES (2,'B'); COMMIT;",
                    "ROLLBACK;", "SAVEPOINT s;", "PRAGMA foreign_keys=OFF;",
                    "ATTACH DATABASE '/tmp/x.db' AS x;"]:
            with self.subTest(sql=sql):
                with self.assertRaises(FarmError):
                    db.execute_write(self.conn, sql)
                self.assertEqual(db.dump(self.conn), self.before)
                self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_empty_sql_is_rejected(self):
        for sql in ["", "  ;  ", "-- just a comment\n", "/* nothing */ ;"]:
            with self.subTest(sql=sql):
                with self.assertRaises(FarmError):
                    db.execute_write(self.conn, sql)

    def test_semicolons_inside_strings_do_not_split_statements(self):
        db.execute_write(self.conn, "INSERT INTO bed VALUES (2, 'a;b'); "
                                    "INSERT INTO bed VALUES (3, 'c;\nd');")
        names = [r[0] for r in self.conn.execute("SELECT name FROM bed ORDER BY id")]
        self.assertEqual(names, ["A", "a;b", "c;\nd"])

    def test_last_statement_may_omit_semicolon(self):
        db.execute_write(self.conn, "INSERT INTO bed VALUES (2, 'B')")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM bed").fetchone()[0], 2)

    def test_insert_into_autoincrement_table_works(self):
        conn = db.load("CREATE TABLE a (id INTEGER PRIMARY KEY AUTOINCREMENT, n TEXT) STRICT;")
        db.execute_write(conn, "INSERT INTO a(n) VALUES ('x');")
        self.assertEqual(conn.execute("SELECT id FROM a").fetchone()[0], 1)

    def test_writes_to_internal_tables_are_rejected(self):
        conn = db.load("CREATE TABLE a (id INTEGER PRIMARY KEY AUTOINCREMENT, n TEXT) STRICT;"
                       "INSERT INTO a(n) VALUES ('x');")
        before = db.dump(conn)
        for sql in ["UPDATE sqlite_sequence SET seq = 100;",
                    "DELETE FROM sqlite_sequence;"]:
            with self.subTest(sql=sql):
                with self.assertRaises(FarmError):
                    db.execute_write(conn, sql)
                self.assertEqual(db.dump(conn), before)

    def test_update_and_delete_work(self):
        db.execute_write(self.conn, "UPDATE bed SET name = 'Z' WHERE id = 1;")
        self.assertEqual(self.conn.execute("SELECT name FROM bed").fetchone()[0], "Z")
        db.execute_write(self.conn, "DELETE FROM bed;")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM bed").fetchone()[0], 0)

    def test_connection_is_usable_after_a_rejected_write(self):
        with self.assertRaises(FarmError):
            db.execute_write(self.conn, "INSERT INTO planting VALUES (1, 99, 'c', 1);")
        db.execute_write(self.conn, "INSERT INTO bed VALUES (2, 'B');")
        self.assertFalse(self.conn.in_transaction)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM bed").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
