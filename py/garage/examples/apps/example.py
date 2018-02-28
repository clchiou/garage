#!/usr/bin/env python3

"""Demonstrate garage.apps."""

from garage import apps


@apps.with_prog('list')
@apps.with_help('list books')
@apps.with_argument('--type', help='book type')
@apps.with_defaults(some_default='default value')
def list_books(args):
    """List books in this room."""
    print('List books of type %s' % args.type)
    return 0


@apps.with_help('manage books')
@apps.with_apps('action', 'application actions', list_books)
def book(args):
    """Manage books in this room."""
    return args.action(args)


@apps.with_prog('search')
@apps.with_help('search books')
@apps.with_argument('--title', help='book title to search for')
def search_books(args):
    """Search books on this shelf."""
    print('Search books of title %s' % args.title)
    return 0


@apps.with_help('do things to book shelves')
@apps.with_apps('action', 'application actions', search_books)
def shelf(args):
    """Do things to book shelves."""
    return args.action(args)


@apps.with_apps('entity', 'application entities', book, shelf)
def main(args):
    print('args = %r' % args)
    return args.entity(args)


if __name__ == '__main__':
    apps.run(main)
