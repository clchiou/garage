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


class LongRunning(actors.Stub, actor=_LongRunning):
    pass


def make_dead_actor(event):
    stub = LongRunning(event)
    stub.kill()
    stub.get_future().result()  # Wait until it's dead.
    return stub


class SupervisorsTest(unittest.TestCase):

    def test_supervisor(self):
        supervisor = supervisors.Supervisor(0, None)
        with self.assertRaises(actors.Exit):
            supervisor.start().result()
        self.assertTrue(supervisor.get_future().done())

        supervisor = supervisors.Supervisor(1, [].pop)
        with self.assertRaises(actors.Exit):
            supervisor.start().result()
        self.assertTrue(supervisor.get_future().done())

        for num_actors in range(2, 10):
            self.run_supervisor_test(
                num_actors,
                num_actors + num_actors // 2 - 1,
            )

    def run_supervisor_test(self, num_actors, num_created):
        self.subTest(num_actors=num_actors, num_created=num_created)

        semaphore = threading.Semaphore(value=0)
        stubs = [LongRunning(semaphore) for _ in range(num_created)]
        for stub in stubs:
            stub.start()

        supervisor = supervisors.Supervisor(num_actors, list(stubs).pop)
        start_future = supervisor.start()

        # Let LongRunning actors exit one by one...
        alive_stubs = {stub.get_future(): stub for stub in stubs}
        while alive_stubs:
            semaphore.release()
            done_futs = futures.wait(
                alive_stubs, return_when=futures.FIRST_COMPLETED,
            ).done
            self.assertTrue(1, len(done_futs))
            done_fut = done_futs.pop()
            self.assertTrue(done_fut.done())
            alive_stubs.pop(done_fut)

        with self.assertRaises(actors.Exit):
            start_future.result()
        self.assertTrue(supervisor.get_future().done())

    def test_supervisor_without_stub(self):
        supervisor = supervisors._Supervisor(0, None)
        with self.assertRaises(actors.Exit):
            supervisor.start()

        supervisor = supervisors._Supervisor(1, [].pop)
        with self.assertRaises(actors.Exit):
            supervisor.start()

        for num_actors in range(2, 10):
            stubs = [make_dead_actor(None) for _ in range(num_actors)]
            supervisor = supervisors._Supervisor(num_actors, stubs.pop)
            with self.assertRaises(actors.Exit):
                supervisor.start()
            self.assertListEqual([], stubs)


if __name__ == '__main__':
    unittest.main()
