"""Calculator client and server."""

import logging
import sys

from g1.asyncs import kernels

from g1.messaging import reqrep
from g1.messaging.reqrep import clients
from g1.messaging.reqrep import servers
from g1.messaging.wiredata import jsons


class Calculator:

    async def add(self, x: float, y: float) -> float:
        del self  # Unused.
        return x + y

    async def sub(self, x: float, y: float) -> float:
        del self  # Unused.
        return x - y

    async def mul(self, x: float, y: float) -> float:
        del self  # Unused.
        return x * y

    @reqrep.raising(ZeroDivisionError)
    async def div(self, x: float, y: float) -> float:
        del self  # Unused.
        return x / y


CalculatorRequest, CalculatorResponse = \
    reqrep.generate_interface_types(Calculator)


@kernels.with_kernel
def main(argv):

    if len(argv) < 3:
        print('usage: %s {client|server} url ...' % argv[0], file=sys.stderr)
        return 1

    if argv[1] == 'client' and len(argv) < 6:
        print('usage: %s client url op x y' % argv[0], file=sys.stderr)
        return 1

    logging.basicConfig(level=logging.DEBUG)

    json_wire_data = jsons.JsonWireData()

    url = argv[2]

    async def run_server():
        app = Calculator()
        with servers.Server(
            app, CalculatorRequest, CalculatorResponse, json_wire_data
        ) as server:
            server.socket.listen(url)
            await server.serve()

    async def run_client():
        with clients.Client(
            CalculatorRequest, CalculatorResponse, json_wire_data
        ) as client:
            client.socket.dial(url)
            op, x, y = argv[3:6]
            method = getattr(client.m, op)
            x = float(x)
            y = float(y)
            print('%s(%f, %f) == %f' % (op, x, y, await method(x=x, y=y)))

    if argv[1] == 'server':
        kernels.run(run_server)
    else:
        kernels.run(run_client)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
