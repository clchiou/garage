__all__ = [
    'make_bdist_zipapp',
]

import distutils.core
import distutils.errors
import distutils.log
import stat
import tempfile
import zipfile
from pathlib import Path


def make_bdist_zipapp(
    *, python='/usr/bin/env python3', main_optional=False, main=None
):
    # pylint: disable=too-many-statements

    class bdist_zipapp(distutils.core.Command):

        PYTHON = python

        MAIN = main
        MAIN_TEMPLATE = (
            '# -*- coding: utf-8 -*-\n'
            'import {module}\n'
            '{module}.{func}()\n'
        )

        description = "create a zipapp distribution"

        user_options = [
            ('python=', None, "python interpreter to use"),
            ('main=', None, "main function of the zipapp"),
            ('output=', None, "output zipapp path"),
        ]

        def __init__(self, dist):
            super().__init__(dist)
            self.python = self.PYTHON
            self.main = self.MAIN
            self.output = None

        def initialize_options(self):
            self.python = self.PYTHON
            self.main = self.MAIN
            self.output = None

        def finalize_options(self):
            if self.python is None:
                raise distutils.errors.DistutilsOptionError(
                    '--python is required'
                )
            if not main_optional and self.main is None:
                raise distutils.errors.DistutilsOptionError(
                    '--main is required'
                )
            if self.output is None:
                raise distutils.errors.DistutilsOptionError(
                    '--output is required'
                )
            self.output = Path(self.output)

        def run(self):
            if self.distribution.has_ext_modules():
                raise distutils.errors.DistutilsPlatformError(
                    'disallow making zipapp with ext module for now'
                )
            with tempfile.TemporaryDirectory(
                dir=self.output.parent,
                prefix=self.output.name + '-',
            ) as build_dir:
                self._run(build_dir)

        def _run(self, build_dir):
            self.run_command('build')

            distutils.log.info('installing to %s' % build_dir)
            install = self.reinitialize_command(
                'install',
                reinit_subcommands=1,
            )
            install.root = build_dir

            # Install lib and data but ignore headers, scripts, and egg
            # info at the moment.
            if self.distribution.has_pure_modules():
                self.run_command('install_lib')
            if self.distribution.has_data_files():
                self.run_command('install_data')

            install_lib = self.distribution.get_command_obj('install_lib')
            install_dir = Path(install_lib.install_dir)

            if self.main is not None:
                main_path = install_dir / '__main__.py'
                module, func = self.main.rsplit(':', maxsplit=1)
                distutils.log.info('generate: %s' % main_path)
                with open(main_path, 'w') as main_file:
                    main_file.write(
                        self.MAIN_TEMPLATE.format(
                            module=module,
                            func=func,
                        )
                    )

            def open_zip_archive(file, mode):
                # It seems that Python interpreter can only load
                # DEFLATE-compressed zip file.
                return zipfile.ZipFile(
                    file,
                    mode=mode,
                    compression=zipfile.ZIP_DEFLATED,
                )

            def add_content(zip_archive):
                for child in install_dir.rglob('*'):
                    arcname = child.relative_to(install_dir)
                    # TODO: This might create duplicated entries (for
                    # example, multiple "g1/" directories).  We probably
                    # should fix this?
                    zip_archive.write(str(child), str(arcname))

            if self.output.exists():
                distutils.log.info('append to: %s' % self.output)
                with open_zip_archive(self.output, 'a') as zip_archive:
                    add_content(zip_archive)
            else:
                distutils.log.info('generate: %s' % self.output)
                with open(self.output, 'wb') as output_file:
                    output_file.write(b'#!%s\n' % self.python.encode('utf-8'))
                    # Call flush() to ensure that zip content is after
                    # shebang.
                    output_file.flush()
                    with open_zip_archive(output_file, 'w') as zip_archive:
                        add_content(zip_archive)

            # Do `chmod a+x`.
            mode = self.output.stat().st_mode
            self.output.chmod(stat.S_IMODE(mode) | 0o111)

    return bdist_zipapp
