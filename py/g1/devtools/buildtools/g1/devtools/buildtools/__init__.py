__all__ = [
    'read_package_config',
]

import collections
import shlex
import subprocess

PackageConfig = collections.namedtuple(
    'PackageConfig',
    'include_dirs library_dirs libraries extra_compile_args',
)


def read_package_config(packages):
    cmd = ['pkg-config', '--cflags', '--libs']
    cmd.extend(packages)
    args = (
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE) \
        .stdout
        .decode('utf8')
    )
    args = shlex.split(args)
    config = {
        'include_dirs': [],
        'library_dirs': [],
        'libraries': [],
        'extra_compile_args': [],
    }
    for arg in args:
        if arg.startswith('-I'):
            config['include_dirs'].append(arg[len('-I'):])
        elif arg.startswith('-L'):
            config['library_dirs'].append(arg[len('-L'):])
        elif arg.startswith('-l'):
            config['libraries'].append(arg[len('-l'):])
        else:
            config['extra_compile_args'].append(arg)
    return PackageConfig(
        **{
            # Use list instead of tuple (``sorted`` returns list) since
            # ``setuptools.extension.Extension`` only accepts list.
            field: sorted(set(value))
            for field, value in config.items()
        }
    )
