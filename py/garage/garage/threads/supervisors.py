__all__ = [
    'supervisor',
]

import logging
from concurrent import futures

from garage import asserts
from garage.threads import actors


LOG = logging.getLogger(__name__)


@actors.OneShotActor.from_func
def supervisor(num_actors, start_new_actor):
    """A supervisor will always keep num_actors long-running actors
       alive at any time; however, if half of actors died, it dies, too.
    """
    # TODO: Implement more re-start/exit strategy.
    asserts.greater(num_actors, 0)
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
                actor_futures[stub._get_future()] = stub
                LOG.info('supervise actor %s', stub._name)

        done_actor_futures = futures.wait(
            actor_futures,
            return_when=futures.FIRST_COMPLETED,
        ).done

        for done_actor_future in done_actor_futures:
            stub = actor_futures.pop(done_actor_future)
            try:
                done_actor_future.result()
            except Exception:
                # If actor raises, say, SystemExit, supervisor will not
                # capture it (and will exit).
                LOG.warning(
                    'actor has crashed: %s',
                    stub._name, exc_info=True,
                )
                num_actors_crashed += 1
            else:
                LOG.debug('actor exited normally: %s', stub._name)
                target -= 1

    if num_actors_crashed >= threshold:
        raise RuntimeError(
            'actors have crashed: %d >= %d' % (num_actors_crashed, threshold))
    LOG.info('exit')
