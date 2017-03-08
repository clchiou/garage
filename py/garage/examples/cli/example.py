#!/usr/bin/env python3

"""Demonstrate garage.cli."""

from garage import cli
from garage.components import ARGS
from garage.startups.threads.executors import ExecutorComponent


@cli.command('list', help='list books')
@cli.argument('--type', help='book type')
@cli.component(ExecutorComponent)
def list_books(args: ARGS):
    """List books in this room."""
    print('List books of type %s' % args.type)


@cli.command(help='manage books')
@cli.sub_command_info('action', 'actions')
@cli.sub_command(list_books)
def book(args: ARGS):
    """Manage books in this room."""
    args.action()


@cli.command('search', help='search books')
@cli.argument('--title', help='book title to search for')
@cli.component(ExecutorComponent)
def search_books(args: ARGS):
    """Search books on this shelf."""
    print('Search books of title %s' % args.title)


@cli.command(help='act on book shelf')
@cli.sub_command_info('action', 'actions')
@cli.sub_command(search_books)
def shelf(args: ARGS):
    """Act on book shelf in this room."""
    args.action()


@cli.command()
@cli.sub_command_info('entity', 'entities')
@cli.sub_command(book)
@cli.sub_command(shelf)
def example(args: ARGS):
    args.entity()


if __name__ == '__main__':
    example()
