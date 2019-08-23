"""Containers.

Based on our (limited) experience with Docker and rkt, we want to design
a container that fits our needs:

* Containerized processes are monitor-able.  When any of them crashed,
  it will be detected and can be automatically restarted.

* The basic unit is pod (of multiple application processes).  When a pod
  is launched, these processes are contained inside the same container
  so that they may access the same file directory tree and (virtual)
  network devices, as if they are running in the same physical machine.

* As a result of the above two requirements, there will be a supervisor
  process monitoring the application processes, and the supervisor is
  then monitored by the system-level process monitor; together these
  forms a supervisor tree.

* Pod and image storage space usage should be clear and easy to manage.
  This requirement is grown from my pain points with rkt that:
  * `rkt image rm` cannot remove rendered images (see:
    https://github.com/rkt/rkt/issues/2890 for details).
  * `rkt image gc` can remove rendered images, but it also removes
    images that might still be used (see:
    https://github.com/rkt/rkt/issues/3387 for relevant info).  From my
    experience, it even removes stage1 image, causing rkt unable to
    start any new pod.

* (Optional?) Pod should be somewhat configurable in the sense that we
  may change some of the parameters while launching the pod (probably
  through environment variables).  In comparison, rkt disallows any
  configuration change overwriting the pod manifest.

The design borrows many ideas from rkt, but should be simpler than rkt
because we do not intend to make our container as general-purposed and
versatile as rkt.  However, due to lack of expertise and development
time, our container will be less secure than Docker or rkt.
"""

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())
