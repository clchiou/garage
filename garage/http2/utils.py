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

from garage.http2 import clients


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


_CHUNK_SIZE = 10 * 1024


class DownloadError(Exception):
    pass


def download(
        *,
        client,
        executor,
        requests_to_filename,
        output_dirpath,
        chunk_size=_CHUNK_SIZE):
    """Store documents from URIs into a directory."""
    _Downloader(
        client,
        executor,
        requests_to_filename,
        output_dirpath,
        chunk_size,
    ).run()


class _Downloader:

    def __init__(self,
                 client,
                 executor,
                 requests_to_filename,
                 output_dirpath,
                 chunk_size):
        self.client = client
        self.executor = executor
        self.requests_to_filename = requests_to_filename
        self.output_dirpath = pathlib.Path(output_dirpath)
        self.tmp_dirpath = self.output_dirpath.with_name(
            self.output_dirpath.name + '.part')
        self.chunk_size = chunk_size

    def run(self):
        proceed = self.prepare()
        if not proceed:
            return
        self.download(self.tmp_dirpath)
        self.check(self.tmp_dirpath)
        self.tmp_dirpath.rename(self.output_dirpath)
        LOG.info('complete %s', self.output_dirpath)

    def prepare(self):
        if self.output_dirpath.is_dir():
            LOG.warning('skip directory %s', self.output_dirpath)
            return False
        if self.output_dirpath.exists():
            raise DownloadError('not a directory %s' % self.output_dirpath)
        if not self.tmp_dirpath.is_dir():
            if self.tmp_dirpath.exists():
                raise DownloadError('not a directory %s' % self.tmp_dirpath)
            self.tmp_dirpath.mkdir(parents=True)
        else:
            LOG.warning('resume download from %s', self.tmp_dirpath)
        return True

    def download(self, write_to_dir):
        dl_futures = []
        for reqs, filename in self.requests_to_filename:
            output_path = write_to_dir / filename
            if output_path.exists():
                LOG.warning('skip file %s', output_path)
                continue
            dl_futures.append(self.executor.submit(
                self.download_to_file, reqs, output_path))
        for dl_future in futures.as_completed(dl_futures):
            dl_future.result()

    def download_to_file(self, reqs, output_path):
        response = self.try_requests(reqs)
        with contextlib.closing(response):
            tmp_output_path = output_path.with_name(output_path.name + '.part')
            with tmp_output_path.open('wb') as output:
                for chunk in response.iter_content(self.chunk_size):
                    output.write(chunk)
            tmp_output_path.rename(output_path)
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
        filenames = set(filename for _, filename in self.requests_to_filename)
        for filepath in write_to_dir.iterdir():
            if filepath.name not in filenames:
                LOG.warning('remove extra file %s', filepath)
                filepath.unlink()
            else:
                filenames.remove(filepath.name)
        if filenames:
            raise DownloadError(
                'could not download these files:\n  %s' %
                '\n  '.join(sorted(filenames)))


def form(client, uri, *,
         form_xpath='//form',
         form_data=None,
         encoding=None,
         kwargs=None):
    """POST to an HTML form."""
    response = client.get(uri, **(kwargs or {}))
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
