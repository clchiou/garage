"""Character encoding error handlers."""

__all__ = [
    'make_error_logger',
]


def make_error_logger(logger):
    """Make handlers that logs and ignores encoding errors."""
    def log_errors(exc):
        logger.error('incorrect character encoding', exc_info=exc)
        return ('', exc.end)
    return log_errors
