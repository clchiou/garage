"""Check whether dependent packages are available."""

import subprocess


python2_available = (
    subprocess.run(['which', 'python2'], stdout=subprocess.DEVNULL)
    .returncode == 0
)


try:
    import curio
except ImportError:
    curio_available = False
else:
    curio_available = True


try:
    import http2
except ImportError:
    http2_available = False
else:
    http2_available = True


try:
    import lxml
except ImportError:
    lxml_available = False
else:
    lxml_available = True


try:
    import nanomsg
except ImportError:
    nanomsg_available = False
else:
    nanomsg_available = True


try:
    import requests
except ImportError:
    requests_available = False
else:
    requests_available = True


try:
    import startup
except ImportError:
    startup_available = False
else:
    startup_available = True


try:
    import yaml
except ImportError:
    yaml_available = False
else:
    yaml_available = True
