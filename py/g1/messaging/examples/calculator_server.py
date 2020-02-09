"""Calculator server using parts."""

import g1.asyncs.servers.parts
import g1.messaging.parts
from g1.apps import asyncs
from g1.apps import utils
from g1.asyncs import kernels
from g1.messaging import reqrep
from g1.messaging.reqrep import servers
from g1.messaging.wiredata import jsons

LABELS = g1.messaging.parts.define_server()


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


@utils.define_maker
def make_server() -> LABELS.server:
    return servers.Server(
        Calculator(),
        CalculatorRequest,
        CalculatorResponse,
        jsons.JsonWireData(),
    )


def main(supervise_servers: g1.asyncs.servers.parts.LABELS.supervise_servers):
    kernels.run(supervise_servers)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
