"""Install OpenJDK."""

import foreman

import shipyard2.rules.bases

shipyard2.rules.bases.define_distro_packages(['openjdk-17-jdk-headless'])

# Nothing to do since we use OpenJDK from the distro.
foreman.define_rule('build').depend('//bases:build').depend('install')
