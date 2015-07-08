__all__ = [
    'memorize',
]


def memorize(method):
    """Wrap a property/method and memorize its return value."""
    is_property = isinstance(method, property)
    wrapped = method
    if is_property:
        method = method.fget

    def wrapper(self):
        if 'value' not in wrapper.__dict__:
            wrapper.value = method(self)
        return wrapper.value

    wrapper.__doc__ = wrapped.__doc__
    return property(wrapper) if is_property else wrapper
