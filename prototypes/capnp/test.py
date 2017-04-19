import contextlib
import io

import extension


# Test 1
boom = extension.Boom()
try:
    boom._reset()
except RuntimeError as e:
    print('Expect RuntimeError from _reset: %r' % e)
else:
    raise AssertionError('_reset() did not raise')


# Test 2
boom = extension.Boom()
error_message = io.StringIO()
with contextlib.redirect_stderr(error_message):
    del boom
error_message = error_message.getvalue()
assert error_message, error_message
print('Expect error from: %r' % error_message)


# Test 3
boom = extension.Boom()
try:
    try:
        raise ValueError
    finally:
        boom._reset()  # Raise RuntimeError
except RuntimeError as e:
    print('Expect error from: %r' % e)


# Test 4
boom = extension.Boom()
try:
    try:
        raise ValueError
    finally:
        del boom  # Do not raise
except ValueError as e:
    print('Expect error from: %r' % e)
