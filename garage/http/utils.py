"""Helper functions, etc."""

__all__ = [
    'DownloadError',
    'download',
    'form',
]

import contextlib
import logging
import pathlib
from concurrent import futures

from garage.http import clients


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


_CHUNK_SIZE = 10 * 1024


class DownloadError(Exception):
    pass


def download(
        *,
        client,
        executor,
        output_dirpath,
        relpath_to_requests,
        strict=True,
        chunk_size=_CHUNK_SIZE):
    """Download documents from URIs.

       relpath_to_requests is a dict-like object that maps relative path
       to a sequence of Request objects or URIs.  download() will try
       the Request objects one by one, and write the result of the first
       successful request to the relative path.  (All paths are relative
       to output_dirpath.)

       While download() is in progress, it writes results to files or
       directories ending with '.part' suffix.  This may help you
       distinguish download-in-progress files from completed ones, and
       this also makes retrying download() safe and efficient in the
       sense that a finished file will not be requested again.

       If strict is true (the default), download() will remove any file
       under output_dirpath that is not in relpath_to_requests.
    """
    _Downloader(
        client,
        executor,
        output_dirpath,
        relpath_to_requests,
        strict,
        chunk_size,
    ).run()


class _Downloader:

    def __init__(self,
                 client,
                 executor,
                 output_dirpath,
                 relpath_to_requests,
                 strict,
                 chunk_size):
        self.client = client
        self.executor = executor
        self.output_dirpath = pathlib.Path(output_dirpath)
        self.relpath_to_requests = {
            pathlib.Path(relpath): reqs
            for relpath, reqs in relpath_to_requests.items()
        }
        self.parts_dirpath = self.output_dirpath.with_name(
            self.output_dirpath.name + '.part')
        self.strict = strict
        self.chunk_size = chunk_size

    def run(self):
        proceed = self.prepare()
        if not proceed:
            return
        self.download(self.parts_dirpath)
        self.check(self.parts_dirpath)
        self.parts_dirpath.rename(self.output_dirpath)
        LOG.info('complete %s', self.output_dirpath)

    def prepare(self):
        if self.output_dirpath.is_dir():
            LOG.warning('skip directory %s', self.output_dirpath)
            return False
        if self.output_dirpath.exists():
            raise DownloadError('not a directory %s' % self.output_dirpath)
        if not self.parts_dirpath.is_dir():
            if self.parts_dirpath.exists():
                raise DownloadError('not a directory %s' % self.parts_dirpath)
            self.parts_dirpath.mkdir(parents=True)
        else:
            LOG.warning('resume download from %s', self.parts_dirpath)
        return True

    def download(self, write_to_dir):
        dl_futures = [
            self.executor.submit(
                self.download_to_file, write_to_dir, relpath, reqs
            )
            for relpath, reqs in self.relpath_to_requests.items()
        ]
        for dl_future in futures.as_completed(dl_futures):
            dl_future.result()

    def download_to_file(self, write_to_dir, relpath, reqs):
        output_path = write_to_dir / relpath
        if output_path.exists():
            LOG.warning('skip file %s', output_path)
            return

        part_relpath = relpath.with_name(relpath.name + '.part')
        if part_relpath in self.relpath_to_requests:
            raise DownloadError(
                'cannot let part-file overwrite file %s' % part_relpath)

        part_path = write_to_dir / part_relpath

        with contextlib.closing(self.try_requests(reqs)) as response:
            try:
                part_path.parent.mkdir(parents=True)
            except FileExistsError:
                if not part_path.parent.is_dir():
                    raise
            if part_path.exists():
                LOG.warning('overwrite part-file %s', part_path)
            with part_path.open('wb') as output:
                for chunk in response.iter_content(self.chunk_size):
                    output.write(chunk)
            part_path.rename(output_path)
        LOG.info('download to %s', output_path)

    def try_requests(self, reqs):
        for req in reqs[:-1]:
            try:
                return self.send_request(req)
            except clients.HttpError:
                pass
        return self.send_request(reqs[-1])

    def send_request(self, req):
        if not isinstance(req, clients.Request):
            req = clients.Request('GET', req)
        return self.client.send(req, stream=True)

    def check(self, write_to_dir):
        output_paths = set(
            write_to_dir / relpath for relpath in self.relpath_to_requests
        )
        for path in sorted(write_to_dir.glob('**/*'), reverse=True):
            if path.is_dir():
                if self.strict and _is_empty_dir(path):
                    LOG.warning('remove empty directory %s', path)
                    path.rmdir()
            elif path not in output_paths:
                if self.strict:
                    LOG.warning('remove extra file %s', path)
                    path.unlink()
            else:
                output_paths.remove(path)
        if output_paths:
            raise DownloadError(
                'could not download these files:\n  %s' %
                '\n  '.join(map(str, sorted(output_paths))))


def _is_empty_dir(path):
    try:
        next(path.iterdir())
    except StopIteration:
        return True
    else:
        return False


def form(client, request, *,
         encoding=None,
         form_xpath='//form',
         form_data=None):
    """POST to an HTML form."""
    if isinstance(request, str):
        request = clients.Request('GET', request)
    response = client.send(request)
    dom_tree = response.dom(encoding=encoding)
    forms = dom_tree.xpath(form_xpath)
    if len(forms) != 1:
        raise ValueError('require one form, not %d' % len(forms))
    form_element = forms[0]
    action = form_element.get('action')
    if form_data is None:
        form_data = {}
    else:
        form_data = dict(form_data)  # Make a copy before modifying it.
    for form_input in form_element.xpath('//input'):
        form_data.setdefault(form_input.get('name'), form_input.get('value'))
    return client.post(action, data=form_data)
