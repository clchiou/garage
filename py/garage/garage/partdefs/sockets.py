from garage import parameters
from garage import parts
from garage import sockets


PARTS = parts.Parts(sockets.__name__)
PARTS.patch_getaddrinfo = parts.AUTO


PARAMS = parameters.define_namespace(sockets.__name__, 'socket utils')
PARAMS.patch_getaddrinfo = parameters.create(
    False, 'enable patching getaddrinfo for caching query results')


@parts.define_maker
def make() -> PARTS.patch_getaddrinfo:
    if PARAMS.patch_getaddrinfo.get():
        sockets.patch_getaddrinfo()
