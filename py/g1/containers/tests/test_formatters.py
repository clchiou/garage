import unittest

import io

from g1.containers import formatters


class FormatterTest(unittest.TestCase):

    def test_stringifiers(self):
        formatter = formatters.Formatter(['x'], stringifiers={'x': hex})
        formatter.append({'x': 0x1})
        formatter.append({'x': 0x12})
        buffer = io.StringIO()
        formatter.output(buffer)
        self.assertEqual(
            buffer.getvalue(),
            'x   \n'
            '0x1 \n'
            '0x12\n',
        )

    def test_column_widths(self):
        formatter = formatters.Formatter(['x', 'y'])
        formatter.append({'x': '', 'y': ''})
        formatter.append({'x': '---', 'y': '--'})
        buffer = io.StringIO()
        formatter.output(buffer)
        self.assertEqual(
            buffer.getvalue(),
            'x   y \n'
            '      \n'
            '--- --\n',
        )

        formatter = formatters.Formatter(['x', 'y'], header=False)
        formatter.append({'x': '', 'y': ''})
        formatter.append({'x': '---', 'y': '--'})
        buffer = io.StringIO()
        formatter.output(buffer)
        self.assertEqual(
            buffer.getvalue(),
            '      \n'
            '--- --\n',
        )

        formatter = formatters.Formatter(['xxxx', 'yyyyy'])
        formatter.append({'xxxx': '', 'yyyyy': ''})
        formatter.append({'xxxx': '---', 'yyyyy': '--'})
        buffer = io.StringIO()
        formatter.output(buffer)
        self.assertEqual(
            buffer.getvalue(),
            'xxxx yyyyy\n'
            '          \n'
            '---  --   \n',
        )

        formatter = formatters.Formatter(['xxxx', 'yyyyy'], header=False)
        formatter.append({'xxxx': '', 'yyyyy': ''})
        formatter.append({'xxxx': '---', 'yyyyy': '--'})
        buffer = io.StringIO()
        formatter.output(buffer)
        self.assertEqual(
            buffer.getvalue(),
            '      \n'
            '--- --\n',
        )

    def test_sort(self):
        formatter = formatters.Formatter(['x'])
        formatter.append({'x': 3})
        formatter.append({'x': 1})
        formatter.append({'x': 2})
        buffer = io.StringIO()
        formatter.output(buffer)
        self.assertEqual(buffer.getvalue(), 'x\n3\n1\n2\n')

        formatter.sort(key=lambda row: row['x'])
        buffer = io.StringIO()
        formatter.output(buffer)
        self.assertEqual(buffer.getvalue(), 'x\n1\n2\n3\n')

    def test_empty_columns(self):
        for kwargs, expect in (
            (
                {
                    'format': formatters.Formats.CSV,
                    'header': False,
                },
                '\r\n',
            ),
            (
                {
                    'format': formatters.Formats.CSV,
                    'header': True,
                },
                '\r\n\r\n',
            ),
            (
                {
                    'format': formatters.Formats.TEXT,
                    'header': False,
                },
                '\n',
            ),
            (
                {
                    'format': formatters.Formats.TEXT,
                    'header': True,
                },
                '\n\n',
            ),
        ):
            with self.subTest(kwargs):
                formatter = formatters.Formatter([], **kwargs)
                formatter.append({'x': 1})
                buffer = io.StringIO()
                formatter.output(buffer)
                self.assertEqual(buffer.getvalue(), expect)


if __name__ == '__main__':
    unittest.main()
