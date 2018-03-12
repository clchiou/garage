import functools
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


def create_client_parts(module_name=None):
    part_list = parts.Parts(module_name)
    part_list.request_queue = parts.AUTO
    return part_list


def create_server_parts(module_name=None):
    part_list = parts.Parts(module_name)
    part_list.request_queue = parts.AUTO
    return part_list


def create_client_params(
        *, bind=(), connect=(), num_sockets=1, capacity=32, timeout=2):
    params = parameters.create_namespace('create NN_REQ client')
    params.bind = parameters.create(
        bind, type=typing.List[str], doc='add URL to bind socket to')
    params.connect = parameters.create(
        connect, type=typing.List[str], doc='add URL to connect socket to')
    params.num_sockets = parameters.create(
        num_sockets, 'set number of client sockets')
    params.capacity = parameters.create(
        capacity, 'set request queue capacity')
    params.timeout = parameters.create(
        timeout, unit='second', doc='set request timeout')
    return params


def create_server_params(*, bind=(), connect=(), capacity=32, timeout=2):
    params = parameters.create_namespace('create NN_REP server')
    params.bind = parameters.create(
        bind, type=typing.List[str], doc='add URL to bind socket to')
    params.connect = parameters.create(
        connect, type=typing.List[str], doc='add URL to connect socket to')
    params.capacity = parameters.create(
        capacity, 'set request queue capacity')
    params.timeout = parameters.create(
        timeout, unit='second', doc='set request timeout')
    return params


def _create_maker(part_list, params, get_num_sockets, make_socket, make_coro):

    def make(
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

        request_queue = queues.Queue(capacity=params.capacity.get())
        exit_stack.callback(request_queue.close)

        sockets = []
        for _ in range(get_num_sockets()):
            socket = exit_stack.enter_context(make_socket())
            for url in bind_addresses:
                socket.bind(url)
            for url in connect_addresses:
                socket.connect(url)
            sockets.append(socket)

        coro = make_coro(
            graceful_exit=graceful_exit,
            sockets=sockets,
            request_queue=request_queue,
            timeout=timeout,
        )

        return coro, request_queue

    return make


def create_client_maker(part_list, params):
    return _create_maker(
        part_list,
        params,
        params.num_sockets.get,
        functools.partial(Socket, protocol=nn.NN_REQ),
        reqrep.client,
    )


def create_server_maker(part_list, params, *, error_handler=None):
    return _create_maker(
        part_list,
        params,
        lambda: 1,
        functools.partial(Socket, domain=nn.AF_SP_RAW, protocol=nn.NN_REP),
        lambda sockets, **kwargs: reqrep.server(
            socket=sockets[0],
            error_handler=error_handler,
            **kwargs,
        ),
    )
