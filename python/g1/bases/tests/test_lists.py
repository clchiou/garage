import unittest

from g1.bases import lists


class ListsTest(unittest.TestCase):

    def test_binary_search(self):
        self.assertEqual(lists.binary_search('a', 'a'), 0)
        self.assertEqual(lists.binary_search('abcdef', 'a'), 0)
        self.assertEqual(lists.binary_search('abcdef', 'c'), 2)
        self.assertEqual(lists.binary_search('abcdef', 'f'), 5)

        self.assertEqual(lists.binary_search('a', 97, key=ord), 0)
        self.assertEqual(lists.binary_search('abcdef', 97, key=ord), 0)
        self.assertEqual(lists.binary_search('abcdef', 99, key=ord), 2)
        self.assertEqual(lists.binary_search('abcdef', 102, key=ord), 5)

        self.assertEqual(lists.binary_search('a', 'a', reverse=True), 0)
        self.assertEqual(lists.binary_search('fedcba', 'a', reverse=True), 5)
        self.assertEqual(lists.binary_search('fedcba', 'c', reverse=True), 3)
        self.assertEqual(lists.binary_search('fedcba', 'f', reverse=True), 0)

        array = list(range(1023))
        for expect, value in enumerate(array):
            with self.subTest((expect, value)):
                self.assertEqual(lists.binary_search(array, value), expect)

        array.reverse()
        for expect, value in enumerate(array):
            with self.subTest((expect, value)):
                self.assertEqual(
                    lists.binary_search(array, value, reverse=True),
                    expect,
                )

        with self.assertRaisesRegex(ValueError, r'not found'):
            lists.binary_search([], 'x')
        with self.assertRaisesRegex(ValueError, r'not found'):
            lists.binary_search('abcdef', 'x')

        with self.assertRaisesRegex(ValueError, r'not found'):
            lists.binary_search([], 'x', reverse=True)
        with self.assertRaisesRegex(ValueError, r'not found'):
            lists.binary_search('fedcba', 'x', reverse=True)

    def test_lower_bound(self):
        self.assertEqual(lists.lower_bound('a', 'a'), 0)
        self.assertEqual(lists.lower_bound('bcdefg', 'a'), 0)
        self.assertEqual(lists.lower_bound('bcdefg', 'b'), 0)
        self.assertEqual(lists.lower_bound('bcdefg', 'd'), 2)
        self.assertEqual(lists.lower_bound('bcdefg', 'g'), 5)
        self.assertEqual(lists.lower_bound('bcdefg', 'h'), 6)

        self.assertEqual(lists.lower_bound('bbbcccdddeee', 'b'), 0)
        self.assertEqual(lists.lower_bound('bbbcccdddeee', 'c'), 3)
        self.assertEqual(lists.lower_bound('bbbcccdddeee', 'd'), 6)
        self.assertEqual(lists.lower_bound('bbbcccdddeee', 'e'), 9)

        self.assertEqual(lists.lower_bound('bbbcccdddeee', 98, key=ord), 0)
        self.assertEqual(lists.lower_bound('bbbcccdddeee', 99, key=ord), 3)
        self.assertEqual(lists.lower_bound('bbbcccdddeee', 100, key=ord), 6)
        self.assertEqual(lists.lower_bound('bbbcccdddeee', 101, key=ord), 9)

        self.assertEqual(
            lists.lower_bound('eeedddcccbbb', 'b', reverse=True), 9
        )
        self.assertEqual(
            lists.lower_bound('eeedddcccbbb', 'c', reverse=True), 6
        )
        self.assertEqual(
            lists.lower_bound('eeedddcccbbb', 'd', reverse=True), 3
        )
        self.assertEqual(
            lists.lower_bound('eeedddcccbbb', 'e', reverse=True), 0
        )

        array = [i for i in range(1023) for j in range(7)]
        for i in range(1023):
            with self.subTest(i):
                self.assertEqual(lists.lower_bound(array, i), i * 7)

        array.reverse()
        for i in range(1023):
            with self.subTest(i):
                self.assertEqual(
                    lists.lower_bound(array, i, reverse=True),
                    (1022 - i) * 7,
                )

    def test_upper_bound(self):
        self.assertEqual(lists.upper_bound('a', 'a'), 1)
        self.assertEqual(lists.upper_bound('bcdefg', 'a'), 0)
        self.assertEqual(lists.upper_bound('bcdefg', 'b'), 1)
        self.assertEqual(lists.upper_bound('bcdefg', 'd'), 3)
        self.assertEqual(lists.upper_bound('bcdefg', 'g'), 6)
        self.assertEqual(lists.upper_bound('bcdefg', 'h'), 6)

        self.assertEqual(lists.upper_bound('bbbcccdddeee', 'b'), 3)
        self.assertEqual(lists.upper_bound('bbbcccdddeee', 'c'), 6)
        self.assertEqual(lists.upper_bound('bbbcccdddeee', 'd'), 9)
        self.assertEqual(lists.upper_bound('bbbcccdddeee', 'e'), 12)

        self.assertEqual(lists.upper_bound('bbbcccdddeee', 98, key=ord), 3)
        self.assertEqual(lists.upper_bound('bbbcccdddeee', 99, key=ord), 6)
        self.assertEqual(lists.upper_bound('bbbcccdddeee', 100, key=ord), 9)
        self.assertEqual(lists.upper_bound('bbbcccdddeee', 101, key=ord), 12)

        self.assertEqual(
            lists.upper_bound('eeedddcccbbb', 'b', reverse=True), 12
        )
        self.assertEqual(
            lists.upper_bound('eeedddcccbbb', 'c', reverse=True), 9
        )
        self.assertEqual(
            lists.upper_bound('eeedddcccbbb', 'd', reverse=True), 6
        )
        self.assertEqual(
            lists.upper_bound('eeedddcccbbb', 'e', reverse=True), 3
        )

        array = [i for i in range(1023) for j in range(7)]
        for i in range(1023):
            with self.subTest(i):
                self.assertEqual(lists.upper_bound(array, i), (i + 1) * 7)

        array.reverse()
        for i in range(1023):
            with self.subTest(i):
                self.assertEqual(
                    lists.upper_bound(array, i, reverse=True),
                    (1023 - i) * 7,
                )


if __name__ == '__main__':
    unittest.main()
