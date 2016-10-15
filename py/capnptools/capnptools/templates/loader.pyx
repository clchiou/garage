def _load(prefix=''):
    % if modules:
    % for module_name in sorted(modules):
    module_name = '%s%s${module_name}' % (prefix, prefix and '.')
    module = sys.modules[module_name] = types.ModuleType(module_name)
    % for node in modules[module_name]:
<%
    comps = node_table.get_classname_comps(node.id)
    classname = comps[-1]
    module_name = '.'.join(comps[:-1])
%>\
    module.${classname} = ${node_table.get_python_classname(node.id)}
    % endfor
    % endfor
    % else:
    pass
    % endif
