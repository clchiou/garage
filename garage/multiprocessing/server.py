"""A server that execute arbitrary Python code."""

# NOTE: This module is Python 2 compatible.

import argparse
import contextlib
import logging
import os
import os.path
import sys
import threading
from multiprocessing.connection import Listener

try:
    import backport
except ImportError:
    from . import backport


LOG = logging.getLogger('multiprocessing.server')
LOG.addHandler(logging.NullHandler())
LOG_FORMAT = '%(asctime)s %(threadName)s %(levelname)s %(name)s: %(message)s'


TIMEOUT = 5.0


def run_server(listener, semaphore):
    exit_flag = threading.Event()
    server_thread = threading.Thread(
        name='multiprocessing',
        target=server,
        args=(listener, semaphore, exit_flag),
    )
    server_thread.daemon = True
    server_thread.start()
    wait_forever(exit_flag)
    LOG.info('exit')


def wait_forever(event):
    # Unfortunately event.wait() without timeout is not uninterruptable.
    while not event.is_set():
        event.wait(3600)


def server(listener, semaphore, exit_flag):
    LOG.info('start server')
    worker_serial = 0
    global_vars = {}
    while not exit_flag.is_set():
        conn = listener.accept()
        try:
            semaphore.acquire(TIMEOUT)
            LOG.debug('accept %r', listener.last_accepted)
            worker = Worker(
                closing(conn),
                semaphore,
                exit_flag,
                global_vars,
                listener.last_accepted,
            )
            worker_serial += 1
            worker_thread = threading.Thread(
                name='multiprocessing-%02d' % worker_serial,
                target=worker.run,
            )
            worker_thread.daemon = True
            worker_thread.start()
            conn = None  # conn is transfered to the worker.
        except backport.Timeout:
            LOG.error('exceed concurrent workers limit')
        finally:
            # Close conn only when it is not transfered to the worker.
            if conn is not None:
                conn.close()
    LOG.info('exit')


class Worker(object):

    VERSION_INFO = {'version_info': tuple(sys.version_info)}

    OKAY = {}
    ERROR_REQUIRE_COMMAND = {'error': 'require command'}
    ERROR_REQUIRE_NAME = {'error': 'require name argument'}
    ERROR_REQUIRE_VALUE = {'error': 'require value argument'}
    ERROR_REQUIRE_SOURCE = {'error': 'require source argument'}

    def __init__(
            self, conn_manager, semaphore, exit_flag, global_vars, address):
        self.conn_manager = conn_manager
        self.semaphore = semaphore
        self.exit_flag = exit_flag
        self.global_vars = global_vars
        if isinstance(address, tuple):
            self.filename = '%s:%s' % (address)
        else:
            self.filename = str(address)

    def run(self):
        LOG.debug('start worker')
        try:
            with self.conn_manager as conn:
                self.serve_forever(conn)
        finally:
            self.semaphore.release()
        LOG.debug('exit')

    def serve_forever(self, conn):
        conn.send(self.VERSION_INFO)
        while not self.exit_flag.is_set():
            if self.process_request(conn):
                break

    def process_request(self, conn):
        try:
            request = conn.recv()
        except EOFError:
            return True

        command = request.get('command')
        LOG.debug('receive command %r', command)
        if not command:
            conn.send(self.ERROR_REQUIRE_COMMAND)
            return

        handler = {
            'shutdown': self.do_shutdown,
            'close': self.do_close,
            'get': self.do_get,
            'set': self.do_set,
            'del': self.do_del,
            'execute': self.do_execute,
            'call': self.do_call,
        }.get(command)
        if handler is None:
            LOG.warning('unknown command %r', command)
            conn.send({'error': 'unknown command', 'command': command})
            return

        try:
            return handler(conn, request)
        except Exception as exc:
            conn.send({'error': 'uncaught exception', 'exception': str(exc)})
            raise

    def do_shutdown(self, conn, _):
        self.exit_flag.set()
        conn.send(self.OKAY)

    def do_close(self, conn, _):
        conn.send(self.OKAY)
        return True

    def do_get(self, conn, request):
        name = request.get('name')
        if not name:
            conn.send(self.ERROR_REQUIRE_NAME)
            return
        if name not in self.global_vars:
            conn.send({'error': 'undefined variable', 'name': name})
            return
        conn.send({'name': name, 'value': self.global_vars[name]})

    def do_set(self, conn, request):
        name = request.get('name')
        if not name:
            conn.send(self.ERROR_REQUIRE_NAME)
            return
        if 'value' not in request:
            conn.send(self.ERROR_REQUIRE_VALUE)
            return
        self.global_vars[name] = request['value']
        conn.send(self.OKAY)

    def do_del(self, conn, request):
        name = request.get('name')
        if not name:
            conn.send(self.ERROR_REQUIRE_NAME)
            return
        if name not in self.global_vars:
            conn.send({'error': 'undefined variable', 'name': name})
            return
        del self.global_vars[name]
        conn.send(self.OKAY)

    def do_execute(self, conn, request):
        if 'source' not in request:
            conn.send(self.ERROR_REQUIRE_SOURCE)
            return
        source = request['source']
        filename = request.get('filename', self.filename)
        try:
            code = compile(source, filename, 'exec')
        except SyntaxError as exc:
            LOG.exception('syntax error in %s', filename)
            conn.send({
                'error': 'syntax error',
                'filename': filename,
                'exception': str(exc),
            })
            return
        try:
            exec(code, self.global_vars)
        except Exception as exc:
            LOG.exception('runtime error in exec %s', filename)
            conn.send({
                'error': 'runtime error',
                'filename': filename,
                'exception': str(exc),
            })
            return
        conn.send(self.OKAY)

    def do_call(self, conn, request):
        name = request.get('name')
        if not name:
            conn.send(self.ERROR_REQUIRE_NAME)
            return
        if name not in self.global_vars:
            conn.send({'error': 'undefined function', 'name': name})
            return
        func = self.global_vars[name]
        args = request.get('args', ())
        kwargs = request.get('kwargs', {})
        try:
            value = func(*args, **kwargs)
        except Exception as exc:
            LOG.exception(
                'runtime error when calling %s(*%r, **%r)', name, args, kwargs)
            conn.send({
                'error': 'runtime error',
                'name': name,
                'exception': str(exc),
            })
            return
        conn.send({'name': name, 'value': value})


def closing(context_manager):
    # Some Python 2 objects are not managed.
    for attr in ('__enter__', '__exit__'):
        if not hasattr(context_manager, attr):
            return contextlib.closing(context_manager)
    return context_manager


def main(argv):
    parser = argparse.ArgumentParser(description="""
    A server that executes arbitrary Python codes.
    """)
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help='verbose output')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--listen-net', metavar=('ADDRESS', 'PORT'), nargs=2,
        help="""listen on AF_INET style address""")
    group.add_argument(
        '--listen-sock', metavar='PATH',
        help="""listen on AF_UNIX or AF_PIPE style path""")
    parser.add_argument(
        '--authkey-var', metavar='VAR', default='AUTHKEY',
        help="""read authkey from this environment variable
                (default %(default)s)""")
    parser.add_argument(
        '--max-workers', type=int, default=8,
        help="""set max concurrent workers""")
    args = parser.parse_args(argv[1:])

    if args.verbose == 0:
        level = logging.WARNING
    elif args.verbose == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG
    logging.basicConfig(level=level, format=LOG_FORMAT)

    if args.listen_net:
        address = (args.listen_net[0], int(args.listen_net[1]))
    else:
        address = args.listen_sock

    authkey = os.getenv(args.authkey_var)
    if authkey is None:
        parser.error('cannot read authkey from %s' % args.authkey_var)
        return 2
    if sys.version_info.major > 2:
        authkey = bytes(authkey, encoding='ascii')

    if args.max_workers <= 0:
        semaphore = backport.UnlimitedSemaphore()
    else:
        semaphore = backport.BoundedSemaphore(args.max_workers)

    threading.current_thread().name = 'multiprocessing.server#main'
    with closing(Listener(address, authkey=authkey)) as listener:
        run_server(listener, semaphore)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
