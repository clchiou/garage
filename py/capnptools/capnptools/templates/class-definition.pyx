# ${display_name}

cdef class ${python_classname}__Builder:

    cdef MessageBuilder _builder
    cdef ${cython_classname}__Builder _data
    % for member in members:
    % if member.is_list:
##  Work around that List_X is not an extension type (because we want
##  List_X to also inherit from Sequence).
    cdef object _builder_${member.name}
    % elif member.is_struct:
    cdef ${member.type_name}__Builder _builder_${member.name}
    % endif
    % endfor

    def __cinit__(self, MessageBuilder builder, object data):
        self._builder = builder
        self._data = dereference(<${cython_classname}__Builder*>PyCapsule_GetPointer(data, NULL))
        % for member in members:
        % if member.is_list or member.is_struct:
        self._builder_${member.name} = None
        % endif
        % endfor

<%include file="class-definition-repr.pyx"/>\

<%include file="class-definition-as-dict.pyx"/>\

    def _as_reader(self):
        cdef ${cython_classname}__Reader data = self._data.asReader()
        return ${python_classname}(self, PyCapsule_New(&data, NULL, NULL))
##
##  Generate members
##
    % for member in members:
##  _is_X()
    % if member.izzer:

<%include file="class-definition-izzer.pyx" args="member=member"/>\
    % endif
##  property(X)

<%include file="class-definition-builder-getter.pyx" args="member=member"/>\
##  X.setter(...)
    % if not member.is_group:

<%include file="class-definition-setter.pyx" args="member=member"/>\
    % endif
##  _init_X()
    % if member.is_struct:

    def _init_${member.name}(self):
        cdef ${member.cython_type_name}__Builder value = self._data.${member.initer}()
        self._builder_${member.name} = ${member.type_name}__Builder(self._builder, PyCapsule_New(&value, NULL, NULL))
        return self._builder_${member.name}
    % endif
##  _init_X(size)
    % if member.is_list:

    def _init_${member.name}(self, unsigned int size):
        cdef ${member.cython_type_name}__Builder value = self._data.${member.initer}(size)
        self._builder_${member.name} = ${member.type_name}__Builder(self._builder, PyCapsule_New(&value, NULL, NULL))
        return self._builder_${member.name}
    % endif
    % endfor

cdef class ${python_classname}:
    % if context.get('nested_types'):

    % for nested_type_name, nested_type_id in nested_types:
    ${nested_type_name} = ${node_table.get_python_classname(nested_type_id)}
    % endfor
    % endif

##  Hold a reference to the _resource to make sure that it is released
##  after this object (_resource could be either a MessageReader or a
##  builder object).
    cdef object _resource
    cdef ${cython_classname}__Reader _data
    % for member in members:
    % if member.is_text:
    cdef str _cache_${member.name}
    % elif member.is_data:
    cdef bytes _cache_${member.name}
    % elif member.is_list:
##  Work around that List_X is not an extension type (because we want
##  List_X to also inherit from Sequence).
    cdef object _cache_${member.name}
    % elif member.is_struct:
    cdef ${member.type_name} _cache_${member.name}
    % endif
    % endfor

    def __cinit__(self, object resource, object data):
        self._resource = resource
        self._data = dereference(<${cython_classname}__Reader*>PyCapsule_GetPointer(data, NULL))
        % for member in members:
        % if member.is_text or member.is_data or member.is_list or member.is_struct:
        self._cache_${member.name} = None
        % endif
        % endfor

<%include file="class-definition-repr.pyx"/>\

<%include file="class-definition-as-dict.pyx"/>\
##
##  Generate members
##
    % for member in members:
    % if member.izzer:

<%include file="class-definition-izzer.pyx" args="member=member"/>\
    % endif
    % if member.getter:

<%include file="class-definition-reader-getter.pyx" args="member=member"/>\
    % endif
    % endfor
