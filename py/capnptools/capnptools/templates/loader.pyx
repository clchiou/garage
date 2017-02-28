def _load(prefix=''):
    % if modules:
    def _load_module(full_path):
        last_module = None
        parts = []
        for part in full_path.split('.'):
            parts.append(part)
            prefix = '.'.join(parts)
            if prefix not in sys.modules:
                sys.modules[prefix] = types.ModuleType(prefix)
            module = sys.modules[prefix]
            if last_module:
                if not hasattr(last_module, part):
                    setattr(last_module, part, module)
            last_module = module
        return module
    % for module_name in sorted(modules):
    module = _load_module('%s%s${module_name}' % (prefix, prefix and '.'))
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
