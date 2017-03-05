__all__ = [
    'start_supervisor',
]

import logging
from concurrent import futures

from garage import asserts
from garage.threads import actors
from garage.threads import utils


LOG = logging.getLogger(__name__)


def start_supervisor(num_actors, start_new_actor):
    return actors.build(supervisor,
                        name=next(start_supervisor.names),
                        set_pthread_name=True,
                        args=(num_actors, start_new_actor))


start_supervisor.names = utils.generate_names(name='supervisor')


@actors.OneShotActor
def supervisor(num_actors, start_new_actor):
    """A supervisor will always keep num_actors long-running actors
       alive at any time; however, if half of actors died, it dies, too.
    """
    # TODO: Implement more re-start/exit strategy.
    asserts.precond(num_actors > 0)
    LOG.info('start')

    actor_futures = {}
    target = num_actors
    threshold = max(1, num_actors // 2)
    num_actors_crashed = 0
    while target > 0 and num_actors_crashed < threshold:

        if target > len(actor_futures):
            # Start actors to meet the target.
            for _ in range(target - len(actor_futures)):
                stub = start_new_actor()
                actor_futures[stub.get_future()] = stub
                LOG.info('supervise actor %s', stub.name)

        done_actor_futures = futures.wait(
            actor_futures,
            return_when=futures.FIRST_COMPLETED,
        ).done

        for done_actor_future in done_actor_futures:
            stub = actor_futures.pop(done_actor_future)
            try:
                done_actor_future.result()
            except BaseException:
                LOG.warning('actor has crashed: %s',
                            stub.name, exc_info=True)
                num_actors_crashed += 1
            else:
                LOG.debug('actor exited normally: %s', stub.name)
                target -= 1

    if num_actors_crashed >= threshold:
        raise RuntimeError('actors have crashed: %d >= %d' %
                           (num_actors_crashed, threshold))
    LOG.info('exit')
