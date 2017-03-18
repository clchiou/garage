from templates import common, py


common.define_git_repo(
    repo='https://github.com/dabeaz/curio.git',
    treeish='0.7',
)


rules = py.define_source_package(package='curio')
rules.build.depend('git_clone')
