# ${display_name}
cdef _make_${python_classname}():
    return enum.IntEnum('${python_classname}', [
        % for member in members:
        ('${member}', <int>${cython_classname}__${member}),
        % endfor
    ])
${python_classname} = _make_${python_classname}()
