"""Cap'n Proto build rule templates."""

import functools


def make_build_cmd(parameters, import_path_labels=()):
    """Build Cap'n Proto schema for Python packages."""
    cmd = ['build']
    if import_path_labels:
        cmd.append('compile_schemas')
        for import_path_label in import_path_labels:
            cmd.append('--import-path')
            cmd.append(parameters[import_path_label])
    return cmd


make_build_cmd.with_import_path_labels = lambda *labels: functools.partial(
    make_build_cmd,
    import_path_labels=labels,
)
