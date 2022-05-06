from foreman import define_rule


COUNT = 0
if COUNT > 0:
    raise AssertionError('load more than once')
COUNT += 1


(define_rule('pkg1')
 .depend('//pkg3:rule_y')
 .reverse_depend('pkg2')
 .reverse_depend('//pkg4:pkg4')
)


define_rule('pkg2')


define_rule('pkg3').depend('pkg2')
