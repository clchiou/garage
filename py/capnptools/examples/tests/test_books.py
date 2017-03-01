import unittest

from examples import books


class BooksTest(unittest.TestCase):

    def test_builder(self):
        book = books.MallocMessageBuilder().init_root(books.Book)
        book.title = 'Moby-Dick; or, The Whale'
        book.authors = ['Herman Melville']
        self.assertEqual(
            {
                'title': 'Moby-Dick; or, The Whale',
                'authors': ['Herman Melville'],
            },
            book._as_dict(),
        )

        book = book._as_reader()
        self.assertEqual('Moby-Dick; or, The Whale', book.title)
        self.assertEqual(['Herman Melville'], book.authors._as_dict())
        self.assertEqual(
            {
                'title': 'Moby-Dick; or, The Whale',
                'authors': ['Herman Melville'],
            },
            book._as_dict(),
        )


if __name__ == '__main__':
    unittest.main()
