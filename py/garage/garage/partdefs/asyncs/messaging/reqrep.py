import logging
import typing

import nanomsg as nn
from nanomsg.curio import Socket

from garage import parameters
from garage import parts
from garage.asyncs import queues
from garage.asyncs.messaging import reqrep
from garage.partdefs import apps
from garage.partdefs.asyncs import servers


def define_parts(module_name):
    return parts.PartList(module_name, [
        ('request_queue', parts.AUTO),
    ])


def define_params(
        *, bind=(), connect=(), num_sockets=1, capacity=32, timeout=2):
    params = parameters.define_namespace(
        'create nanomsg socket client object')
    params.bind = parameters.define(
        bind, type=typing.List[str], doc='add URL to bind socket to')
    params.connect = parameters.define(
        connect, type=typing.List[str], doc='add URL to connect socket to')
    params.num_sockets = parameters.define(
        num_sockets, 'set number of client sockets')
    params.capacity = parameters.define(
        capacity, 'set request queue capacity')
    params.timeout = parameters.define(
        timeout, unit='second', doc='set request timeout')
    return params


def define_maker(part_list, params):

    def make_client(
            exit_stack: apps.PARTS.exit_stack,
            graceful_exit: servers.PARTS.graceful_exit,
        ) -> (servers.PARTS.server, part_list.request_queue):

        bind_addresses = params.bind.get()
        connect_addresses = params.connect.get()
        if not bind_addresses and not connect_addresses:
            logging.getLogger(reqrep.__name__).warning(
                'socket for queue %s has address to bind or connect to',
                part_list.request_queue,
            )

        # NOTE: Don't use socket timeout (NN_SNDTIMEO and NN_RCVTIMEO)
        # because we are using non-blocking sockets.
        timeout = params.timeout.get()
        if timeout <= 0:
            timeout = None  # No timeout.

        sockets = []
        for _ in range(params.num_sockets.get()):
            request_queue = queues.Queue(capacity=params.capacity.get())
            exit_stack.callback(request_queue.close)
            socket = exit_stack.enter_context(Socket(protocol=nn.NN_REQ))
            for url in bind_addresses:
                socket.bind(url)
            for url in connect_addresses:
                socket.connect(url)
            sockets.append(socket)

        coro = reqrep.client(
            graceful_exit=graceful_exit,
            sockets=sockets,
            request_queue=request_queue,
            timeout=timeout,
        )

        return coro, request_queue

    return make_client
