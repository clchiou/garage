"""Patch pyyaml for zipapp and remove native extension."""

from foreman import get_relpath, rule, to_path

from templates import common

from garage import scripts


common.define_git_repo(
    repo='https://github.com/yaml/pyyaml.git',
    treeish='b6cbfeec35e019734263a8f4e6a3340e94fe0a4f',
)


PATCHES = (
    '0001-add-bdist-zipapp.patch',
)


@rule
@rule.depend('//base:build')
@rule.depend('//host/buildtools:install')
@rule.depend('git_clone')
def patch(parameters):
    drydock_src = parameters['//base:drydock'] / get_relpath()
    for patch_filename in PATCHES:
        dst_patch_path = drydock_src / patch_filename
        if dst_patch_path.exists():
            continue
        patch_path = to_path(patch_filename)
        with scripts.directory(drydock_src), \
                patch_path.open('rb') as patch_file, \
                scripts.redirecting(stdin=patch_file):
            scripts.execute(['patch', '-p1'])
        scripts.cp(patch_path, dst_patch_path)
