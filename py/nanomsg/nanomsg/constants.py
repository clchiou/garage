__all__ = [
    'NN_MSG',
    # Extend in _load().
]

from collections import defaultdict, namedtuple
from ctypes import byref, sizeof
from enum import IntEnum, unique

from . import _nanomsg as _nn


NN_MSG = -1


NanomsgVersion = namedtuple('NanomsgVersion', 'current revision age')


def _load(global_vars, exposed_names):
    int_enum_decls = [
        ('Domain', 'NN_NS_DOMAIN', True),
        ('Transport', 'NN_NS_TRANSPORT', True),
        ('Protocol', 'NN_NS_PROTOCOL', True),
        ('OptionLevel', 'NN_NS_OPTION_LEVEL', True),
        ('SocketOption', 'NN_NS_SOCKET_OPTION', True),
        ('TransportOption', 'NN_NS_TRANSPORT_OPTION', False),
        ('OptionType', 'NN_NS_OPTION_TYPE', True),
        ('OptionUnit', 'NN_NS_OPTION_UNIT', True),
        ('Flag', 'NN_NS_FLAG', True),
        ('Error', 'NN_NS_ERROR', True),
    ]

    symbols = _load_symbols()

    syms = symbols['NN_NS_VERSION']
    global_vars['NS_VERSION'] = NanomsgVersion(
        current=_find_value_by_name(syms, 'NN_VERSION_CURRENT'),
        revision=_find_value_by_name(syms, 'NN_VERSION_REVISION'),
        age=_find_value_by_name(syms, 'NN_VERSION_AGE'),
    )
    exposed_names.append('NS_VERSION')

    for name, namespace, is_unique in int_enum_decls:
        syms = symbols[namespace]
        int_enum = IntEnum(name, syms, module=__name__)
        if is_unique:
            int_enum = unique(int_enum)
        global_vars[name] = int_enum
        exposed_names.append(name)

    for name, value in symbols['NN_NS_LIMIT']:
        global_vars[name] = value
        exposed_names.append(name)


def _load_symbols():
    namespace_names = {}
    namespace_symbols = defaultdict(list)
    for sym in _iter_symbols():
        if sym.ns == 0:
            name = sym.name.decode('ascii')
            if not name.startswith('NN_NS_'):
                raise AssertionError(name)
            namespace_names[sym.value] = name
        else:
            namespace_symbols[sym.ns].append(sym)
    symbols = {}
    for index, name in namespace_names.items():
        syms = namespace_symbols[index]
        symbols[name] = [(sym.name.decode('ascii'), sym.value) for sym in syms]
    return symbols


def _iter_symbols():
    i = 0
    while True:
        sym = _nn.nn_symbol_properties()
        size = _nn.nn_symbol_info(i, byref(sym), sizeof(sym))
        if size == 0:
            break
        if size != sizeof(sym):
            raise AssertionError('expect %d instead %d' % (sizeof(sym), size))
        yield sym
        i += 1


def _find_value_by_name(symbols, target):
    for name, value in symbols:
        if name == target:
            return value
    raise ValueError('%s not in %r' % (target, symbols))


_load(globals(), __all__)
