__all__ = [
    'wait_actor',
    'kill_and_wait_proc',
]

import logging


LOG = logging.getLogger(__name__)


def wait_actor(actor):
    exc = actor._get_future().exception()
    if exc:
        LOG.error('actor %s has crashed', actor._name, exc_info=exc)


def kill_and_wait_proc(proc, timeout=5):
    ret = proc.poll()
    if ret is None:
        LOG.info('terminate process: pid=%d', proc.pid)
        proc.terminate()
        ret = proc.wait(timeout=timeout)
    if ret is None:
        LOG.info('kill process: pid=%d', proc.pid)
        proc.kill()
        ret = proc.wait()
    if ret != 0:
        LOG.error('process err: pid=%d return=%d', proc.pid, ret)
