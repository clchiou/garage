"""Common test fixtures."""

from pathlib import Path

import foreman


class PrepareForeman:

    def setUp(self):
        searcher = foreman.Searcher([Path('/path/to/rules')])
        loader = foreman.LOADER = foreman.Loader(searcher)
        loader.path = Path('path/to/rules')
        self.__loader, foreman.LOADER = foreman.LOADER, loader

    def tearDown(self):
        self.__loader, foreman.LOADER = None, self.__loader

    @property
    def loader(self):
        return foreman.LOADER
