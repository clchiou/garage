import contextlib
import io

import extension


boom = extension.Boom()

error_message = io.StringIO()
with contextlib.redirect_stderr(error_message):
    del boom

error_message = error_message.getvalue()
assert error_message, error_message

print('Error message from destructor: %r' % error_message)
