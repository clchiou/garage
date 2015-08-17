__all__ = [
    'start_supervisor',
]

import logging
from concurrent import futures

from garage.threads import actors
from garage.threads import utils


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


def start_supervisor(num_actors, start_new_actor):
    stub = actors.build(Supervisor,
                        name=next(start_supervisor.names),
                        args=(num_actors, start_new_actor))
    # Make sure that a supervisor does not accept any new messages, and
    # dies immediately after start() returns.
    stub.start()
    stub.kill()
    return stub


start_supervisor.names = utils.generate_names(name='%s#supervisor' % __name__)


class _Supervisor:
    # TODO: Implement more re-start/exit strategy.

    def __init__(self, num_actors, start_new_actor):
        self.num_actors = num_actors
        self.num_actors_died = 0
        self.start_new_actor = start_new_actor

    @actors.method
    def start(self):
        LOG.info('start')

        actor_futures = {}
        num_actors_crashed = 0
        while self.num_actors_died < self.num_actors // 2:

            for _ in range(self.num_actors - len(actor_futures)):
                stub = self.start_new_actor()
                actor_futures[stub.get_future()] = stub
                LOG.info('supervise actor %s', stub.name)

            done_actor_futures = futures.wait(
                actor_futures,
                return_when=futures.FIRST_COMPLETED,
            ).done

            self.num_actors_died += len(done_actor_futures)
            for done_actor_future in done_actor_futures:
                stub = actor_futures.pop(done_actor_future)
                try:
                    done_actor_future.result()
                except BaseException:
                    LOG.warning('actor has crashed: %s',
                                stub.name, exc_info=True)
                    num_actors_crashed += 1

        if (num_actors_crashed > 0 and
                num_actors_crashed >= self.num_actors // 2):
            raise RuntimeError('actors have crashed: %d/%d' %
                               (num_actors_crashed, self.num_actors))
        LOG.info('exit')
        raise actors.Exit


class Supervisor(actors.Stub, actor=_Supervisor):
    """A supervisor will always keep num_actors long-running actors
       alive at any time; however, if half of actors died, it dies, too.
    """
