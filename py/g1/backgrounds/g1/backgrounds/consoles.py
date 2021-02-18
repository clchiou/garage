"""Open a persistent console over a socket.

NOTE: While it is very useful to open a console in a server process, be
very careful about opening one because anyone who can connect to the
console may execute arbitrary Python code in the server process, which
is a huge security vulnerability.
"""

import code as _code  # Rename to avoid conflict with method argument.
import contextlib
import io
import itertools
import logging
import socket
import tempfile
import threading
from pathlib import Path

import g1.asyncs.agents.parts
from g1.apps import asyncs
from g1.apps import parameters
from g1.apps import utils
from g1.asyncs.bases import adapters
from g1.bases import labels
from g1.bases.assertions import ASSERT
from g1.networks import servers
from g1.networks.servers import sockets
from g1.threads import futures

LOG = logging.getLogger(__name__)


class SocketConsoleHandler:

    _COUNTER = itertools.count(1).__next__

    def __init__(self, banner=None, exitmsg=None):
        self._banner = banner
        self._exitmsg = exitmsg
        # `_locals` is persist across and shared among SocketConsole
        # objects.  So concurrent accesses among consoles will interfere
        # each other; be careful!
        self._locals = {}

    async def __call__(self, sock, address):
        del address  # Unused.
        # Undo non-blocking set by SocketAdapter because we are using
        # this socket in a worker thread.
        sock.target.setblocking(True)
        future = futures.Future()
        thread = threading.Thread(
            target=futures.wrap_thread_target(self._run_console, future),
            name='console-%02d' % self._COUNTER(),
            args=(sock.target, ),
            # Set daemon to true because I do not know how to shut down
            # a console thread on exit (for now we do NOT join it when
            # the handler coroutine gets cancelled).
            daemon=True,
        )
        thread.start()
        await adapters.FutureAdapter(future).get_result()

    def _run_console(self, sock):
        LOG.info('console session start: %s', sock)
        console = SocketConsole(sock, self._locals)
        console.interact(self._banner, self._exitmsg)
        LOG.info('console session end')


class SocketConsole(_code.InteractiveConsole):
    """Console over a socket."""

    def __init__(self, sock, *args):
        super().__init__(*args)
        self.__sock = sock
        self.__buffer = []
        self.__lines = []

    def raw_input(self, prompt=''):
        self.write(prompt)
        line = self._read_line()
        # Log every line of console input since console can be a
        # security vulnerability.
        LOG.info('console input: %r', line)
        return line

    def _read_line(self):
        while not self.__lines:
            data = self.__sock.recv(512)
            if not data:
                if self.__buffer:
                    self.__decode_buffer()
                self.__lines.append(None)
                break
            while data:
                i = data.find(b'\n')
                if i < 0:
                    self.__buffer.append(data)
                    break
                if i == len(data) - 1:
                    self.__buffer.append(data)
                    self.__decode_buffer()
                    break
                i += 1
                self.__buffer.append(data[:i])
                self.__decode_buffer()
                data = data[i:]
        if self.__lines[0] is None:
            raise EOFError
        return self.__lines.pop(0)

    def __decode_buffer(self):
        ASSERT.not_empty(self.__buffer)
        data = b''.join(self.__buffer)
        self.__buffer.clear()
        if data.endswith(b'\r\n'):
            data = data[:-2]
        elif data.endswith(b'\n'):
            data = data[:-1]
        self.__lines.append(data.decode('utf-8'))

    def write(self, data):
        try:
            data = data.encode('utf-8')
            num_sent = 0
            while num_sent < len(data):
                num_sent += self.__sock.send(data[num_sent:])
        except BrokenPipeError:
            pass

    # HACK: We have to override InteractiveInterpreter.runcode because
    # `exec` does not return a result and so `runcode` cannot call
    # self.write on it.
    def runcode(self, code):
        buffer = io.StringIO()
        try:
            # XXX: This is bad.  We redirect stdout, which may interfere
            # other threads that happens to be writing to stdout at the
            # same time.  But I do not have any better idea for now.
            with contextlib.redirect_stdout(buffer):
                exec(code, self.locals)  # pylint: disable=exec-used
        except SystemExit:
            raise
        except:  # pylint: disable=bare-except
            self.showtraceback()
        output = buffer.getvalue()
        # Log every line of console input since console can be a
        # security vulnerability.
        LOG.info('console output: %r', output)
        self.write(output)


#
# Part definition.
#
# For now we keep this simple and restrict it to only support Unix
# domain sockets.
#

CONSOLE_LABEL_NAMES = (
    # Private.
    'params',
)


def define_console(module_path=None, **kwargs):
    module_path = module_path or __name__
    module_labels = labels.make_labels(module_path, *CONSOLE_LABEL_NAMES)
    setup_console(
        module_labels,
        parameters.define(module_path, make_console_params(**kwargs)),
    )
    return module_labels


def setup_console(module_labels, module_params):
    utils.depend_parameter_for(module_labels.params, module_params)
    utils.define_maker(
        make_console,
        {
            'params': module_labels.params,
        },
    )


def make_console_params(
    *,
    enable=False,
    socket_dir_path=None,
    socket_file_prefix='console-',
):
    return parameters.Namespace(
        'configure console server',
        enable=parameters.make_parameter(
            enable,
            bool,
        ),
        socket_dir_path=parameters.make_parameter(
            socket_dir_path,
            Path,
            convert=Path,
            validate=Path.is_absolute,
            format=str,
        ),
        socket_file_prefix=parameters.make_parameter(
            socket_file_prefix,
            str,
        ),
    )


def make_console(
    exit_stack: asyncs.LABELS.exit_stack,
    agent_queue: g1.asyncs.agents.parts.LABELS.agent_queue,
    shutdown_queue: g1.asyncs.agents.parts.LABELS.shutdown_queue,
    params,
):
    if not params.enable.get():
        return
    # Use mktemp because when binding to a unix domain socket, it is an
    # error when file exists.
    socket_path = tempfile.mktemp(
        dir=ASSERT.predicate(params.socket_dir_path.get(), Path.is_dir),
        prefix=params.socket_file_prefix.get(),
    )
    exit_stack.callback(Path(socket_path).unlink, missing_ok=True)
    server = servers.SocketServer(
        exit_stack.enter_context(
            sockets.make_server_socket(socket_path, family=socket.AF_UNIX),
        ),
        SocketConsoleHandler(banner='', exitmsg=''),
    )
    agent_queue.spawn(server.serve)
    shutdown_queue.put_nonblocking(server.shutdown)
