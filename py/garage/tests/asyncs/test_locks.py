import unittest

from garage.asyncs.locks import ReadWriteLock
from garage.asyncs.utils import synchronous


class LocksTest(unittest.TestCase):

    @synchronous
    async def test_read_lock(self):
        rwlock = ReadWriteLock()
        self.assertFalse(rwlock.read_lock.locked())
        self.assertFalse(rwlock.write_lock.locked())
        async with rwlock.read_lock:
            self.assertFalse(rwlock.read_lock.locked())
            self.assertTrue(rwlock.write_lock.locked())
            async with rwlock.read_lock:
                self.assertFalse(rwlock.read_lock.locked())
                self.assertTrue(rwlock.write_lock.locked())
        self.assertFalse(rwlock.read_lock.locked())
        self.assertFalse(rwlock.write_lock.locked())

    @synchronous
    async def test_write_lock(self):
        rwlock = ReadWriteLock()
        self.assertFalse(rwlock.read_lock.locked())
        self.assertFalse(rwlock.write_lock.locked())
        async with rwlock.write_lock:
            self.assertTrue(rwlock.read_lock.locked())
            self.assertTrue(rwlock.write_lock.locked())
        self.assertFalse(rwlock.read_lock.locked())
        self.assertFalse(rwlock.write_lock.locked())


if __name__ == '__main__':
    unittest.main()
