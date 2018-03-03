"""Parts of a process.

Here you may:
  * Define list of part names that a module may make, even recursively.
  * Refer to parts by name.
  * Register maker of parts.
  * Assemble parts.

The `parts` module will replace the `components` module as the way to
assemble pieces of a process.

What about the name "parts"?  It is said that a component is usually
self-contained but a part might be not; so these pieces are called parts
instead of components, as they might not be self-contained (also it is
easier to type "part" than "component").
"""

__all__ = [
    'AUTO',
    'PartList',
    'assemble',
    'register_maker',
]

import inspect
from collections import defaultdict
from collections import namedtuple

from garage.assertions import ASSERT

from startup import Startup


AUTO = object()


def _assert_name(name):
    ASSERT.type_of(name, str)
    ASSERT(
        not name.startswith('_'),
        'expect name not start with underscore: %s', name,
    )
    return name


# Make it a subclass of str so that `startup` accepts it.
class PartName(str):
    """Represent a part's name.

    It is composed of a module name and a name, joined by a colon.
    """

    __slots__ = ('_colon_index',)

    def __new__(cls, module_name, name):
        # Handle `[name]`-style annotation of name.
        if isinstance(name, list) and len(name) == 1:
            name = name[0]
        self = super().__new__(cls, ':'.join((
            module_name,
            _assert_name(name),
        )))
        self._colon_index = len(module_name)
        return self

    def __repr__(self):
        return '<%s.%s \'%s\'>' % (
            self.__module__, self.__class__.__qualname__,
            self,
        )

    @property
    def module_name(self):
        return self[:self._colon_index]

    @property
    def name(self):
        return self[self._colon_index+1:]

    def _rebase(self, module_name, prefix):
        """Replace the module name and prepend a prefix."""
        return PartName(
            module_name,
            '.'.join((_assert_name(prefix), self.name)),
        )


class PartList:
    """List of part names.

    To create a part list, you provide the module name and a list of
    entries where each entry is either a name or another part list:
        # Assume __name__ == 'some.module'
        PartList(__name__, [
            ('name_1', AUTO),
            ('name_2', 'some_part_name'),
            ('sub_list', another_part_list),
        ])

    Then you may refer to these part names like this:
        assert part_list.name_1 == 'some.module:name_1'
        assert part_list.name_2 == 'some.module:some_part_name'

    NOTE: If another part list is referred in the list, it will be
    copied and rebased (i.e., all part names will be nested under the
    new part list).
    """

    def __repr__(self):
        return '<%s.%s 0x%x %s>' % (
            self.__module__, self.__class__.__qualname__, id(self),
            ' '.join(
                '%s=%s' % (attr_name, self.__dict__[attr_name])
                for attr_name in self._attr_names
            ),
        )

    def __init__(self, module_name, entries):
        self._attr_names = []
        for attr_name, entry in entries:
            _assert_name(attr_name)
            if entry is AUTO:
                value = PartName(module_name, attr_name)
            elif isinstance(entry, PartList):
                value = entry._rebase(module_name, attr_name)
            elif isinstance(entry, PartName):
                value = entry
            else:
                value = PartName(module_name, entry)
            self.__dict__[attr_name] = value
            self._attr_names.append(attr_name)

    def _rebase(self, module_name, prefix):
        """Rebase part names recursively."""
        # HACK: Call PartList constructor with empty entries, and then
        # fill the entries here to prevent "double" recursion.
        part_list = PartList(None, ())
        for attr_name in self._attr_names:
            value = self.__dict__[attr_name]
            part_list.__dict__[attr_name] = value._rebase(module_name, prefix)
            part_list._attr_names.append(attr_name)
        return part_list


MakerSpec = namedtuple('MakerSpec', [
    'input_specs',  # List of InputSpec.
    'output_specs',  # List of part names that this function makes.
])


InputSpec = namedtuple('InputSpec', [
    'parameter',  # Name of function's parameter.
    'part_name',  # Part name annotated to this parameter.
    'is_all'  # True if it is `[x]`-annotated.
])


def parse_maker_spec(maker):
    """Return MakerSpec of `maker`."""

    sig = inspect.signature(maker)

    input_specs = []
    for parameter in sig.parameters.values():
        if parameter.annotation is sig.empty:
            # We should probably not err out here because maker could be
            # a wrapper, and this parameter is bound to some default (if
            # not, eventually an error will be raised when this maker is
            # called).
            continue
        is_all = isinstance(parameter.annotation, list)
        if is_all:
            ASSERT(
                len(parameter.annotation) == 1,
                'expect `[x]`-form annotation, not: %r', parameter.annotation,
            )
            part_name = parameter.annotation[0]
        else:
            part_name = parameter.annotation
        input_specs.append(InputSpec(
            parameter=parameter.name,
            part_name=ASSERT.type_of(part_name, str),
            is_all=is_all,
        ))
    input_specs = tuple(input_specs)

    if sig.return_annotation is sig.empty:
        # While a maker should usually be annotated with return values,
        # we let the caller decide whether the case of no annotation is
        # an error or not.
        output_specs = ()
    elif isinstance(sig.return_annotation, tuple):
        output_specs = tuple(
            ASSERT.type_of(output_part_name, str)
            for output_part_name in sig.return_annotation
        )
    else:
        output_specs = (ASSERT.type_of(sig.return_annotation, str),)

    return MakerSpec(
        input_specs=input_specs,
        output_specs=output_specs,
    )


# Table of output part name -> maker -> list of input part names.
_MAKER_TABLE = defaultdict(dict)


def register_maker(maker):
    """Register a part maker function."""
    return _register_maker(_MAKER_TABLE, maker)


def _register_maker(maker_table, maker):
    maker_spec = parse_maker_spec(maker)
    ASSERT(
        maker_spec.output_specs,
        'expect maker be annotated on its return value: %r', maker,
    )
    for output_part_name in maker_spec.output_specs:
        maker_table[output_part_name][maker] = [
            input_spec.part_name
            for input_spec in maker_spec.input_specs
        ]
    return maker


def assemble(part_names, *, input_parts=None, selected_makers=None):
    """Assemble parts.

    For each part name, it searches registered part maker (recursively)
    and assembles the (sub-)parts.

    You may provide parts that no maker are registered for via the
    `input_parts` argument.

    If there are multiple registered makers for a part, either one of
    the following will happen:
      * Some makers are selected by the caller.
      * All makers are selected by the caller.
      * An error is raised.
    The `selected_makers` argument looks like this:
        selected_makers = {
            part_name: [maker, ...],  # Some makers are selected.
            another_part_name: all,  # All makers are selected.
        }

    NOTE: It is an error when both an input part is provided and a maker
    is registered for that part name.
    """
    return _assemble(
        _MAKER_TABLE,
        part_names,
        input_parts or {},
        selected_makers or {},
    )


def _assemble(maker_table, part_names, input_parts, selected_makers):
    startup = Startup()
    sources = find_sources(
        part_names,
        input_parts,
        maker_table, selected_makers,
    )
    for maker, pair in sources:
        if maker:
            startup(maker)
        else:
            startup.set(pair[0], pair[1])
    return startup.call()


def find_sources(part_names, input_parts, maker_table, selected_makers):
    """For each part name, find its source recursively.

    A source is either a maker, or a part provided by the caller.
    """

    part_names = set(part_names)

    seen_part_names = set()

    yielded_makers = set()

    def maybe_yield_maker(maker, input_part_names):
        if maker not in yielded_makers:
            part_names.update(input_part_names)
            yielded_makers.add(maker)
            yield maker, None

    while part_names:

        part_name = part_names.pop()
        if part_name in seen_part_names:
            continue

        seen_part_names.add(part_name)

        # No maker is registered for this part; try input parts.
        if part_name not in maker_table:
            ASSERT(
                part_name in input_parts,
                'expect part %s from caller', part_name,
            )
            yield None, (part_name, input_parts[part_name])
            continue

        # Try registered maker(s).
        ASSERT(
            part_name not in input_parts,
            'expect part %s by maker, not from caller', part_name,
        )
        maker_to_input_part_names = maker_table[part_name]

        # Easy, only one maker is registered for this part.
        if len(maker_to_input_part_names) == 1:
            yield from maybe_yield_maker(
                *next(iter(maker_to_input_part_names.items())))
            continue

        # It is getting complex as multiple makers are registered for
        # this part.
        selected = selected_makers.get(part_name)
        ASSERT(
            selected is not None,
            'expect caller to select maker(s) for %s', part_name,
        )

        # Okay, the caller wants them all.
        if selected is all:
            for maker, input_part_names in maker_to_input_part_names.items():
                yield from maybe_yield_maker(maker, input_part_names)
            continue

        # Try the selected makers.
        for maker in selected:
            input_part_names = maker_to_input_part_names.get(maker)
            ASSERT(
                input_part_names is not None,
                'expect maker to be registered: %r', maker,
            )
            yield from maybe_yield_maker(maker, input_part_names)
