# Bootstrap a builder system.

FROM ubuntu:15.10

MAINTAINER Che-Liang Chiou <clchiou@gmail.com>

ARG ANSIBLE_REPO=https://github.com/ansible/ansible.git
ARG ANSIBLE_VERSION=HEAD

RUN apt-get update \
    # Minimum packages for installing Ansible.
 && apt-get --yes install \
      build-essential \
      git \
      python \
      python-dev \
      python-setuptools \
      sudo \
    # Add user `plumber` and grant password-less sudo to him.
 && adduser --disabled-password --gecos "" plumber \
 && echo >> /etc/sudoers \
 && echo "# Allow plumber to execute any command, password-less" \
      >> /etc/sudoers \
 && echo "plumber ALL=(ALL:ALL) NOPASSWD: ALL" >> /etc/sudoers \
    # Check out Ansible.
 && sudo --login --user plumber \
      bash -c "git clone ${ANSIBLE_REPO}" \
 && sudo --login --user plumber \
      bash -c "cd ansible && git checkout ${ANSIBLE_VERSION}" \
 && sudo --login --user plumber \
      bash -c "cd ansible && git submodule update --init --recursive" \
    # Install Ansible.
 && cd /home/plumber/ansible \
 && python setup.py install

USER plumber
WORKDIR /home/plumber
CMD ["/bin/bash"]
