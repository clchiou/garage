__all__ = [
    'ensure_only_one_row',
    'insert_or_ignore',
]


def ensure_only_one_row(rows):
    row = rows.fetchone()
    if row is None or rows.fetchone() is not None:
        raise KeyError
    return row


def insert_or_ignore(conn, table, values):
    conn.execute(table.insert().prefix_with('OR IGNORE'), values)
