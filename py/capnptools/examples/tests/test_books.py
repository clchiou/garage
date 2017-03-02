import unittest

import os
import tempfile

from examples import books


class BooksTest(unittest.TestCase):

    BOOK = {
        'title': 'Moby-Dick; or, The Whale',
        'authors': ['Herman Melville'],
    }

    def test_builder(self):

        book = books.MallocMessageBuilder().init_root(books.Book)
        book.title = self.BOOK['title']
        book.authors = self.BOOK['authors']
        self.assertEqual(self.BOOK, book._as_dict())

        book = book._as_reader()
        self.assertEqual(self.BOOK['title'], book.title)
        self.assertEqual(self.BOOK['authors'], book.authors._as_dict())
        self.assertEqual(self.BOOK, book._as_dict())

    def test_write(self):

        builder = books.MallocMessageBuilder()
        book = builder.init_root(books.Book)
        book.title = self.BOOK['title']
        book.authors = self.BOOK['authors']

        for read_cls, write_func in [
                ('StreamFdMessageReader', 'write_to'),
                ('PackedFdMessageReader', 'write_packed_to')]:

            with self.subTest(read_cls=read_cls, write_func=write_func):
                fd, path = tempfile.mkstemp()
                try:
                    getattr(builder, write_func)(fd)
                    os.close(fd)

                    fd = os.open(path, os.O_RDONLY)
                    reader = getattr(books, read_cls)(fd)
                    book = reader.get_root(books.Book)
                    self.assertEqual(self.BOOK, book._as_dict())

                finally:
                    os.unlink(path)
                    os.close(fd)


if __name__ == '__main__':
    unittest.main()
