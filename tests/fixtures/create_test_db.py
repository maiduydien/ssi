"""Build a tiny isolated DuckDB database for repository tests."""
import duckdb


def create_test_database(path):
    con = duckdb.connect(str(path))
    try:
        con.execute("""
            CREATE TABLE vn30f1m_ticks (
                DateTime TIMESTAMP,
                Price DOUBLE,
                Volume BIGINT,
                ID VARCHAR,
                MarketOrderType VARCHAR
            )
        """)
        con.execute("""
            INSERT INTO vn30f1m_ticks VALUES
            ('2026-10-01 09:00:01', 1900, 2, 'A001', 'B'),
            ('2026-10-01 09:00:02', 1901, 3, 'A002', 'M'),
            ('2026-10-01 09:00:03', 1898, 1, 'A003', 'B'),
            ('2026-10-01 09:00:45', 1902, 4, 'A004', 'M')
        """)
    finally:
        con.close()
