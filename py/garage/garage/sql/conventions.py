__all__ = [
    'make_table_name',
]


def make_table_name(short_name, prefix='', suffix=''):
    return '%s%s%s%s%s' % (
        prefix,
        '_' if prefix else '',
        short_name,
        '_' if suffix else '',
        suffix,
    )
