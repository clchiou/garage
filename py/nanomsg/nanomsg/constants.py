__all__ = [
    'NN_MSG',
    'NANOMSG_OPTION_METADATA',
    # Extend in _load().
]

from collections import defaultdict, namedtuple
from ctypes import byref, sizeof
from enum import IntEnum, unique

from . import _nanomsg as _nn


NN_MSG = -1


NANOMSG_OPTION_METADATA = {}


NanomsgVersion = namedtuple('NanomsgVersion', 'current revision age')


def _load(global_vars, exposed_names):
    int_enum_decls = [
        # enum class         namespace                  unique  global
        ('Domain',          'NN_NS_DOMAIN',             True,   True),
        ('Transport',       'NN_NS_TRANSPORT',          True,   True),
        ('Protocol',        'NN_NS_PROTOCOL',           True,   True),
        ('OptionLevel',     'NN_NS_OPTION_LEVEL',       True,   True),
        ('SocketOption',    'NN_NS_SOCKET_OPTION',      True,   True),
        ('TransportOption', 'NN_NS_TRANSPORT_OPTION',   False,  True),
        ('OptionType',      'NN_NS_OPTION_TYPE',        True,   False),
        ('OptionUnit',      'NN_NS_OPTION_UNIT',        True,   False),
        ('Flag',            'NN_NS_FLAG',               True,   True),
        ('Error',           'NN_NS_ERROR',              True,   False),
    ]

    symbols = _load_symbols()

    syms = symbols['NN_NS_VERSION']
    global_vars['NS_VERSION'] = NanomsgVersion(
        current=_find_value_by_name(syms, 'NN_VERSION_CURRENT'),
        revision=_find_value_by_name(syms, 'NN_VERSION_REVISION'),
        age=_find_value_by_name(syms, 'NN_VERSION_AGE'),
    )
    exposed_names.append('NS_VERSION')

    for enum_name, namespace, is_unique, in_global in int_enum_decls:
        syms = symbols[namespace]
        int_enum = IntEnum(
            enum_name,
            [(name, sym.value) for name, sym in syms],
            module=__name__,
        )

        if is_unique:
            int_enum = unique(int_enum)

        global_vars[enum_name] = int_enum
        exposed_names.append(enum_name)

        # Promote enum members to the global namespace if they are
        # useful to library users.
        if in_global:
            global_vars.update(int_enum.__members__)
            exposed_names.extend(int_enum.__members__)

    for name, sym in symbols['NN_NS_LIMIT']:
        global_vars[name] = sym.value
        exposed_names.append(name)

    _build_metadata(
        symbols['NN_NS_SOCKET_OPTION'],
        global_vars['SocketOption'],
        global_vars['OptionType'],
        global_vars['OptionUnit'],
    )

    _build_metadata(
        symbols['NN_NS_TRANSPORT_OPTION'],
        global_vars['TransportOption'],
        global_vars['OptionType'],
        global_vars['OptionUnit'],
    )

    if len(set(exposed_names)) != len(exposed_names):
        raise AssertionError('names conflict: %r' % exposed_names)


def _build_metadata(symbols, enum_type, option_types, option_units):
    symbols = dict(symbols)
    for member in enum_type:
        sym = symbols[member.name]
        metadata = (option_types(sym.type), option_units(sym.unit))
        NANOMSG_OPTION_METADATA[member.name] = metadata


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
        symbols[name] = [(sym.name.decode('ascii'), sym) for sym in syms]
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
    for name, symbol in symbols:
        if name == target:
            return symbol.value
    raise ValueError('%s not in %r' % (target, symbols))


_load(globals(), __all__)
