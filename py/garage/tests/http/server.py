__all__ = [
    'change_dir',
    'suppress_stderr',
    'start_server',
]

import contextlib
import http.server
import io
import os
import socketserver
import sys
import threading


@contextlib.contextmanager
def change_dir(path):
    cwd = os.getcwd()
    os.chdir(str(path))
    try:
        yield path
    finally:
        os.chdir(cwd)


@contextlib.contextmanager
def suppress_stderr():
    target = io.StringIO()
    stderr = sys.stderr
    sys.stderr = target
    try:
        yield stderr, target
    except BaseException:
        print(target.getvalue(), file=stderr)
        raise
    finally:
        sys.stderr = stderr


@contextlib.contextmanager
def start_server():
    httpd = socketserver.TCPServer(
        ('127.0.0.1', 8000), http.server.SimpleHTTPRequestHandler,
    )
    thread = threading.Thread(name='httpd', target=httpd.serve_forever)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()
