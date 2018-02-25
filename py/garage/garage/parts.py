"""Parts of a process.

Here you may:
  * Define list of part names that a module produces, even recursively.
  * Refer to these part names from another module.
  * Search and assemble parts.

The `parts` module will replace the `components` module as the way to
assemble a process.

What about the name "parts"?  It is said that a component is usually
self-contained but a part might be not; so these pieces are called parts
instead of components, as they might not be self-contained (also it is
easier to type "part" than "component").
"""

__all__ = [
    'PartList',
    'auto',
]

from garage.assertions import ASSERT


auto = object()


def _assert_name(name):
    ASSERT.type_of(name, str)
    ASSERT(
        not name.startswith('_'),
        'expect name not start with underscore: %s', name,
    )
    return name


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
    """List of part names."""

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
            if entry is auto:
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
