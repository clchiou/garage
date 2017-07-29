__all__ = [
    'NN_MSG',
    # Extend in _load().
]

from collections import defaultdict, namedtuple
from ctypes import byref, sizeof
import enum

from . import _nanomsg as _nn


NN_MSG = -1


NanomsgVersion = namedtuple('NanomsgVersion', 'current revision age')


#
# Instead of using a plain int object as enum members, we use this
# wrapper class because Enum treats members with the same value as
# alias (and symbol values may be the same).
#
class Symbol(int):

    def __new__(cls, name, value):
        self = super().__new__(cls, value)
        self.name = name
        return self

    def __str__(self):
        return '<%s: %d>' % (self.name, self)

    __repr__ = __str__

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        if not isinstance(other, Symbol):
            return False
        return self.name == other.name

    def __ne__(self, other):
        return not self.__eq__(other)


def _load(global_vars, exposed_names):

    symbols = _load_symbols()

    # Create NS_VERSION.

    syms = dict(symbols['NN_NS_VERSION'])
    global_vars['NS_VERSION'] = NanomsgVersion(
        current=syms['NN_VERSION_CURRENT'],
        revision=syms['NN_VERSION_REVISION'],
        age=syms['NN_VERSION_AGE'],
    )
    exposed_names.append('NS_VERSION')

    # Create NN_NS_LIMIT.

    for name, sym in symbols['NN_NS_LIMIT']:
        global_vars[name] = sym.value
        exposed_names.append(name)

    # Create enum for the rest of namespaces.

    # Use IntEnum when possible.
    enum_decls = [
        # enum name         namespace                   enum type       export?
        ('Domain',          'NN_NS_DOMAIN',             enum.IntEnum,   True),
        ('Transport',       'NN_NS_TRANSPORT',          enum.IntEnum,   True),
        ('Protocol',        'NN_NS_PROTOCOL',           enum.IntEnum,   True),
        ('OptionLevel',     'NN_NS_OPTION_LEVEL',       enum.IntEnum,   True),
        ('SocketOption',    'NN_NS_SOCKET_OPTION',      enum.Enum,      True),
        ('TransportOption', 'NN_NS_TRANSPORT_OPTION',   enum.Enum,      True),
        ('OptionType',      'NN_NS_OPTION_TYPE',        enum.IntEnum,   True),
        ('OptionUnit',      'NN_NS_OPTION_UNIT',        enum.IntEnum,   True),
        ('Flag',            'NN_NS_FLAG',               enum.Enum,      True),
        # Don't export error because we will create exception classes
        # for them.
        ('Error',           'NN_NS_ERROR',              enum.IntEnum,   False),
        ('Event',           'NN_NS_EVENT',              enum.IntEnum,   True),
        ('Statistic',       'NN_NS_STATISTIC',          enum.IntEnum,   True),
    ]

    for enum_name, namespace, enum_type, export_members in enum_decls:

        syms = symbols[namespace]

        if enum_type is enum.Enum:
            enum_class = enum.Enum(
                enum_name,
                [(name, Symbol(name, sym.value)) for name, sym in syms],
                module=__name__,
            )
        else:
            assert enum_type is enum.IntEnum
            enum_class = enum.IntEnum(
                enum_name,
                [(name, sym.value) for name, sym in syms],
                module=__name__,
            )

        # Check if members are unique (no alias).
        enum_class = enum.unique(enum_class)

        global_vars[enum_name] = enum_class
        exposed_names.append(enum_name)

        if export_members:
            global_vars.update(enum_class.__members__)
            exposed_names.extend(enum_class.__members__)

    # Sanity check...
    if len(set(exposed_names)) != len(exposed_names):
        raise AssertionError('names conflict: %r' % exposed_names)

    # Attach option type and unit to the options.

    OptionType = global_vars['OptionType']
    OptionUnit = global_vars['OptionUnit']

    SocketOption = global_vars['SocketOption']
    for name, sym in symbols['NN_NS_SOCKET_OPTION']:
        option = SocketOption[name].value
        option.type = OptionType(sym.type)
        option.unit = OptionUnit(sym.unit)

    TransportOption = global_vars['TransportOption']
    for name, sym in symbols['NN_NS_TRANSPORT_OPTION']:
        option = TransportOption[name].value
        option.type = OptionType(sym.type)
        option.unit = OptionUnit(sym.unit)


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
