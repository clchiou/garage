from pathlib import Path

from foreman import define_parameter, rule, get_relpath
import foreman


if __name__ != 'pkg1':
    raise AssertionError(__name__)


if not __file__.endswith('foreman/tests/testdata/test_command/pkg1/build.py'):
    raise AssertionError(__file__)


relpath = get_relpath()
if relpath != Path('pkg1'):
    raise AssertionError(relpath)


define_parameter('par1').with_derive(lambda ps: get_relpath())


@rule
@rule.depend('//pkg1/pkg2:rule2')
def rule1(parameters):

    relpath = get_relpath()
    if relpath != Path('pkg1'):
        raise AssertionError(relpath)

    par1 = parameters['par1']
    if par1 != Path('pkg1'):
        raise AssertionError(par1)

    par2 = parameters['//pkg1/pkg2:par2']
    if par2 != Path('pkg1/pkg2'):
        raise AssertionError(par2)

    # test_build() will check this
    foreman._test_ran = True
