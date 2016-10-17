    def __str__(self):
        cdef bytes data = self._data.toString().flatten().cStr()
        return data.decode('utf8')

    def __repr__(self):
        return '<{}.{} object at 0x{:x} of \'{}\'>'.format(self.__class__.__module__, self.__class__.__qualname__, id(self), str(self))
