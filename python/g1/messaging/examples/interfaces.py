from g1.messaging import reqrep
from g1.messaging.reqrep import clients
from g1.messaging.reqrep import inprocs
from g1.messaging.reqrep import servers
from g1.messaging.wiredata import jsons


class Calculator:
    # pylint: disable=no-self-use

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


def make_client():
    return clients.Client(
        CalculatorRequest,
        CalculatorResponse,
        jsons.JsonWireData(),
    )


def make_inproc_server():
    return inprocs.InprocServer(
        Calculator(),
        CalculatorRequest,
        CalculatorResponse,
    )


def make_server():
    return servers.Server(
        Calculator(),
        CalculatorRequest,
        CalculatorResponse,
        jsons.JsonWireData(),
    )
