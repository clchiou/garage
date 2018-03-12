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
    'Parts',
    'assemble',
    'define_maker',
    'define_makers',
    'define_part',
]

import functools
import inspect
from collections import OrderedDict
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
    pass


class Parts:
    """List of part names.

    To create a part list, you (optionally) provide the module name, and
    then assign each part as follows:
      # Assume __name__ == 'some.module'
      part_list = Parts(__name__)
      part_list.name_1 = AUTO
      part_list.name_2 = 'some_part_name'
      part_list.sub_list = another_part_list

    Then you may refer to these part names like this:
      assert part_list.name_1 == 'some.module:name_1'
      assert part_list.name_2 == 'some.module:some_part_name'

    A part list is either orphaned or adopted.  If it is an orphan, you
    cannot read its part names.  It is adopted if it is created with a
    module name, or is assigned to a non-orphan part list.  A part list
    can only be adopted once.
    """

    def __init__(self, module_name=None):
        super().__setattr__('_parent', module_name)
        super().__setattr__('_part_names', OrderedDict())
        super().__setattr__('_resolved', None)

    def __repr__(self):
        return '<%s.%s 0x%x %s>' % (
            self.__module__, self.__class__.__qualname__, id(self),
            ' '.join(
                '%s=%s' % (attr_name, part_name)
                for attr_name, part_name in self._part_names.items()
            ),
        )

    def __getattr__(self, attr_name):
        _assert_name(attr_name)
        try:
            part_name = self._part_names[attr_name]
        except KeyError:
            msg = '%r has no part %r' % (self.__class__.__name__, attr_name)
            raise AttributeError(msg) from None
        if part_name.__class__ is str:
            self._part_names[attr_name] = part_name = self._resolve(part_name)
        return part_name

    def __setattr__(self, attr_name, part_name):
        if attr_name in self.__dict__:
            return super().__setattr__(attr_name, part_name)
        _assert_name(attr_name)
        if part_name is AUTO:
            part_name = attr_name
        if isinstance(part_name, Parts):
            part_name._adopt_by(self, attr_name)
        else:
            ASSERT.is_(part_name.__class__, str)
        self._part_names[attr_name] = part_name

    def _adopt_by(self, parent, edge):
        ASSERT(not self._parent, 'expect orphan: %r', self)
        self._parent = (parent, edge)

    def _resolve(self, part_name):
        if not self._resolved:
            module_name = None
            pieces = []
            obj = self
            while True:
                parent = obj._parent
                ASSERT(parent, 'expect non-orphan: %r, %r', self, obj)
                if isinstance(parent, str):
                    module_name = parent
                    break
                else:
                    obj, edge = parent
                    pieces.append(edge)
            if pieces:
                pieces.reverse()
                self._resolved = '%s:%s.' % (module_name, '.'.join(pieces))
            else:
                self._resolved = module_name + ':'
        return PartName(self._resolved + part_name)


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


# Table of output part name -> maker -> list of InputSpec.
_MAKER_TABLE = defaultdict(dict)


def define_makers(makers):
    """Register a collection of part maker functions."""
    for maker in makers:
        define_maker(maker)


def define_maker(maker):
    """Register a part maker function."""
    return _define_maker(_MAKER_TABLE, maker)


def _define_maker(maker_table, maker):
    maker_spec = parse_maker_spec(maker)
    ASSERT(
        maker_spec.output_specs,
        'expect maker be annotated on its return value: %r', maker,
    )
    for output_part_name in maker_spec.output_specs:
        maker_table[output_part_name][maker] = maker_spec.input_specs
    return maker


def define_part(part_name, *part):
    """Register a part.

    You either call it as a decorator, like,
      @define_part(part_name)
      def part():
          pass
    Or as a "define" expression, like,
      part = define_part(part_name, part)

    NOTE: This is just a wrapper of define_maker because `Startup.set`
    does not support setting values multiple times at the moment.
    """

    if not part:
        return functools.partial(define_part, part_name)

    ASSERT.equal(1, len(part))
    part = part[0]

    def make_part() -> part_name:
        return part

    define_maker(make_part)

    return part


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

    `assemble` errs when there are multiple sources for one part unless
    either caller explicitly allows it or a maker is annotated with [x]
    on the part (a source is either a maker provide the part of an input
    part provided by caller).  This restriction is to protect the case
    when accidentally multiple parts are produced, but only one of them
    is consumed.
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

    queue = []
    for part_name in part_names:
        if isinstance(part_name, InputSpec):
            is_all = part_name.is_all
            part_name = part_name.part_name
        elif isinstance(part_name, list):
            ASSERT.equal(1, len(part_name))
            part_name = part_name[0]
            is_all = True
        else:
            is_all = False
        queue.append((ASSERT.type_of(part_name, str), is_all))

    seen_part_names = set()

    yielded_makers = set()

    def maybe_yield_maker(maker, input_specs):
        if maker not in yielded_makers:
            for input_spec in input_specs:
                queue.append((input_spec.part_name, input_spec.is_all))
            yielded_makers.add(maker)
            yield maker, None

    while queue:

        part_name, is_all = queue.pop(0)
        if part_name in seen_part_names:
            continue

        seen_part_names.add(part_name)

        maker_to_input_specs = maker_table.get(part_name)
        if maker_to_input_specs is None:
            # No maker is registered for this part; try input parts.
            ASSERT(
                part_name in input_parts,
                'expect part %s from caller', part_name,
            )
            yield None, (part_name, input_parts[part_name])
            continue

        # Okay, some makers are registered for this part; let's check
        # whether we want them all or not.

        selected = selected_makers.get(part_name)
        if selected is all:
            is_all = True

        if is_all:
            # We want them all; let's check input part before we check
            # registered makers.
            if part_name in input_parts:
                yield None, (part_name, input_parts[part_name])
        else:
            # Assert that there is only one source - the maker.
            ASSERT(
                part_name not in input_parts,
                'expect part %s by maker, not from caller', part_name,
            )

        if is_all or len(maker_to_input_specs) == 1:
            for maker, input_specs in maker_to_input_specs.items():
                yield from maybe_yield_maker(maker, input_specs)
            continue

        # It is getting complex as multiple makers are registered for
        # this part, and we don't want them all.
        ASSERT(
            selected is not None,
            'expect caller to select maker(s) for %s', part_name,
        )
        for maker in selected:
            input_specs = maker_to_input_specs.get(maker)
            ASSERT(
                input_specs is not None,
                'expect maker to be registered: %r', maker,
            )
            yield from maybe_yield_maker(maker, input_specs)
