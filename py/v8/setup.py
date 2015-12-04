import os
import os.path

from setuptools import find_packages, setup


# distutils and setuptools are VERY brittle - I can't extend the `build`
# and `develop` command to link V8 natives and snapshot blob without
# breaking anything.  To workaround this difficulty, I will just get
# those file paths from environment variable and do the linking myself.


V8_NATIVES_BLOB = os.getenv('V8_NATIVES_BLOB')
V8_SNAPSHOT_BLOB = os.getenv('V8_SNAPSHOT_BLOB')
if None in (V8_NATIVES_BLOB, V8_SNAPSHOT_BLOB):
    raise RuntimeError('V8_NATIVES_BLOB and V8_SNAPSHOT_BLOB are required')


path_pairs = [
    (V8_NATIVES_BLOB, 'v8/_v8/data/natives_blob.bin'),
    (V8_SNAPSHOT_BLOB, 'v8/_v8/data/snapshot_blob.bin'),
]
for src, dst in path_pairs:
    if not os.path.exists(src):
        raise RuntimeError('%s does not exist' % src)
    if os.path.lexists(dst):
        if os.path.samefile(src, dst):
            continue
        else:
            raise RuntimeError('%s exists' % dst)
    print('linking %s -> %s', src, dst)
    os.symlink(src, dst)


setup(
    name = 'v8',
    license = 'MIT',
    packages = find_packages(exclude=['tests*']),
    package_data = {
        'v8': [
            '_v8/data/natives_blob.bin',
            '_v8/data/snapshot_blob.bin',
        ],
    },
    install_requires = [
        'garage',
    ],
)
