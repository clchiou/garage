__all__ = [
    'Items',
]

from garage.functools import nondata_property
from garage.sql.utils import insert_or_ignore, make_select_by


class Items:
    """A thin layer on top of tables of two columns: (id, value)"""

    def __init__(self, table, id_name, value_name):
        self.table = table
        self.value_name = value_name
        self._select_ids = make_select_by(
            getattr(self.table.c, value_name),
            getattr(self.table.c, id_name),
        )

    @nondata_property
    def conn(self):
        raise NotImplementedError

    def select_ids(self, values):
        return dict(self._select_ids(self.conn, values))

    def insert(self, values):
        insert_or_ignore(self.conn, self.table, [
            {self.value_name: value} for value in values
        ])
