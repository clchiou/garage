import unittest

import threading
from concurrent import futures

from garage.threads import actors
from garage.threads import supervisors


class _LongRunning:

    def __init__(self, semaphore):
        self.semaphore = semaphore

    @actors.method
    def start(self):
        self.semaphore.acquire()
        raise actors.Exit

    @actors.method
    def boom(self):
        self.semaphore.acquire()
        raise Exception


class LongRunning(actors.Stub, actor=_LongRunning):
    pass


def make_dead_actor(event):
    stub = LongRunning(event)
    stub.kill()
    stub.get_future().result()  # Wait until it's dead.
    return stub


class SupervisorsTest(unittest.TestCase):

    def test_supervisor(self):
        for num_actors in range(1, 10):
            with self.subTest(num_actors=num_actors):
                self.run_supervisor_test(num_actors, num_actors)

    def run_supervisor_test(self, num_actors, num_created):
        semaphore = threading.Semaphore(value=0)
        stubs = [LongRunning(semaphore) for _ in range(num_created)]
        for stub in stubs:
            stub.start()

        stubs_copy = list(stubs)
        supervisor = supervisors.supervisor(num_actors, stubs_copy.pop)

        # Let LongRunning actors exit one by one...
        self.release_one_by_one(stubs, semaphore)

        self.assertIsNone(supervisor.get_future().result())
        self.assertTrue(supervisor.get_future().done())

        # Exhaust all actors...
        self.assertListEqual([], stubs_copy)

    def test_supervisor_on_error(self):
        num_actors = 4
        num_created = num_actors + num_actors // 2 + 1

        semaphore = threading.Semaphore(value=0)
        stubs = [LongRunning(semaphore) for _ in range(num_created)]
        for i, stub in enumerate(stubs):
            if i <= num_actors // 2:
                stub.boom()
            else:
                stub.start()

        supervisor = supervisors.supervisor(
            num_actors, list(reversed(stubs)).pop)

        # Let LongRunning actors raise one by one...
        self.release_one_by_one(stubs, semaphore)

        with self.assertRaisesRegex(RuntimeError, 'actors have crashed'):
            supervisor.get_future().result()
        self.assertTrue(supervisor.get_future().done())

    def release_one_by_one(self, stubs, semaphore):
        alive_stubs = {stub.get_future(): stub for stub in stubs}
        while alive_stubs:
            semaphore.release()
            done_futures = futures.wait(
                alive_stubs, return_when=futures.FIRST_COMPLETED,
            ).done
            self.assertTrue(1, len(done_futures))
            done_future = done_futures.pop()
            self.assertTrue(done_future.done())
            alive_stubs.pop(done_future)

    def test_supervisor_without_stub(self):
        for num_actors in range(1, 10):
            stubs = [make_dead_actor(None) for _ in range(num_actors)]
            supervisors.supervisor.actor(num_actors, stubs.pop)
            self.assertListEqual([], stubs)


if __name__ == '__main__':
    unittest.main()
