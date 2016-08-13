from foreman import define_rule


COUNT = 0
if COUNT > 0:
    raise AssertionError('load more than once')
COUNT += 1


(define_rule('joint-rule-1')
 .depend('build-rule-1')
)


# If you resolve only joint-rule-2, build-rule-1 should not be added
# through reverse dependency.
define_rule('joint-rule-2')


(define_rule('build-rule-1')
 .reverse_depend('joint-rule-1')
 .reverse_depend('joint-rule-2')
)
