"""Define a global executor for background jobs."""

import g1.threads.parts

LABELS = g1.threads.parts.define_executor(
    __name__,
    name_prefix='bg',
    # Set daemon to True because we assume you don't care to join
    # background jobs on process exit.
    daemon=True,
)
