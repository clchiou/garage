__all__ = [
    'insert_or_ignore',
]


def insert_or_ignore(conn, table, values):
    conn.execute(table.insert().prefix_with('OR IGNORE'), values)
