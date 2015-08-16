__all__ = [
    'Supervisor',
]

import logging
from concurrent import futures

from garage.threads import actors
from garage.threads import utils


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


class _Supervisor:
    # TODO: Implement more re-start/exit strategy.

    def __init__(self, num_actors, make_actor):
        self.num_actors = num_actors
        self.num_actors_died = 0
        self.make_actor = make_actor

    @actors.method
    def start(self):
        LOG.info('start')

        actor_futures = set()
        while self.num_actors_died < self.num_actors // 2:

            for _ in range(self.num_actors - len(actor_futures)):
                stub = self.make_actor()
                actor_futures.add(stub.get_future())
                LOG.info('supervise actor %s', stub.name)

            done_actor_futures = futures.wait(
                actor_futures,
                return_when=futures.FIRST_COMPLETED,
            ).done

            self.num_actors_died += len(done_actor_futures)
            for done_actor_future in done_actor_futures:
                try:
                    done_actor_future.result()
                except BaseException:
                    LOG.warning('a actor has crashed due to', exc_info=True)
                actor_futures.remove(done_actor_future)

        LOG.info('exit')
        raise actors.Exit


class Supervisor(actors.Stub, actor=_Supervisor):
    """A supervisor will always keep num_actors long-running actors
       alive at any time; however, if half of actors died, it dies, too.
    """

    names = utils.generate_names(name='%s#supervisor' % __name__)

    @classmethod
    def make(cls, num_actors, make_actor):
        stub = actors.build(
            cls, name=next(cls.names), args=(num_actors, make_actor))
        # Make sure that a supervisor does not accept any new messages,
        # and dies immediately after start() returns.
        stub.start()
        stub.kill()
        return stub
