"""Format and output columns of data."""

__all__ = [
    'Formats',
    'Formatter',
]

import csv
import enum

from g1.bases.assertions import ASSERT


class Formats(enum.Enum):
    CSV = enum.auto()
    TEXT = enum.auto()


class Formatter:

    def __init__(
        self,
        columns,
        *,
        format=Formats.TEXT,  # pylint: disable=redefined-builtin
        header=True,
        stringifiers=None,
    ):
        self._format = ASSERT.isinstance(format, Formats)
        self._header = header
        self._columns = columns
        self._stringifiers = stringifiers or {}
        self._rows = []

    def append(self, row):
        self._rows.append(row)

    def sort(self, key):
        self._rows.sort(key=key)

    def output(self, output_file):
        columns = [(column, self._stringifiers.get(column, str))
                   for column in self._columns]
        rows = [[stringifier(row[column])
                 for column, stringifier in columns]
                for row in self._rows]
        if self._format is Formats.CSV:
            self._output_csv(rows, output_file)
        else:
            ASSERT.is_(self._format, Formats.TEXT)
            self._output_text(rows, output_file)

    def _output_csv(self, rows, output_file):
        writer = csv.writer(output_file)
        if self._header:
            writer.writerow(self._columns)
        for row in rows:
            writer.writerow(row)

    def _output_text(self, rows, output_file):
        if self._header:
            column_widths = list(map(len, self._columns))
        else:
            column_widths = [0 for _ in range(len(self._columns))]
        for row in rows:
            for i, cell in enumerate(row):
                column_widths[i] = max(column_widths[i], len(cell))
        row_format = ' '.join(
            '{{{}:<{}}}'.format(i, w) for i, w in enumerate(column_widths)
        )
        if self._header:
            output_file.write(row_format.format(*self._columns))
            output_file.write('\n')
        for row in rows:
            output_file.write(row_format.format(*row))
            output_file.write('\n')
