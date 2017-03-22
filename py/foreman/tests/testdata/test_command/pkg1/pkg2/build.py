from pathlib import Path

from foreman import define_parameter, rule, get_relpath


if __name__ != 'pkg1.pkg2':
    raise AssertionError(__name__)


if not __file__.endswith('foreman/tests/testdata/test_command/pkg1/pkg2/build.py'):
    raise AssertionError(__file__)


relpath = get_relpath()
if relpath != Path('pkg1/pkg2'):
    raise AssertionError(relpath)


define_parameter('par2').with_derive(lambda ps: get_relpath())


@rule
def rule2(parameters):

    relpath = get_relpath()
    if relpath != Path('pkg1/pkg2'):
        raise AssertionError(relpath)

    par2 = parameters['par2']
    if par2 != Path('pkg1/pkg2'):
        raise AssertionError(par2)
