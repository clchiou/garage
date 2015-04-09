"""Helper for downloading URIs."""

__all__ = [
    'download',
]

import concurrent.futures
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests.exceptions

from startup import startup

from garage import ARGS
from garage import PARSE
from garage import PARSER
from garage import D

from garage.concurrent import prepare_crash
from garage.http.client import HttpClient
from garage.http.error import DownloadError


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


CHUNK_SIZE = 1024


@startup
def add_arguments(parser: PARSER) -> PARSE:
    group = parser.add_argument_group(__name__)
    group.add_argument(
        '--http-download-chunk-size', type=int, default=CHUNK_SIZE,
        help='set http download chunk size (default %(default)s bytes)')


@startup
def configure_chunk_size(args: ARGS):
    global CHUNK_SIZE
    CHUNK_SIZE = args.http_download_chunk_size


def download(
        *,
        uris_filenames,
        output_dirpath,
        http_client=None,
        max_workers=None,
        chunk_size=None):
    output_dirpath = Path(output_dirpath)
    http_client = http_client or HttpClient.make()
    max_workers = max_workers or D['JOBS']
    chunk_size = chunk_size or CHUNK_SIZE
    okay, tmp_dirpath = _prepare(output_dirpath)
    if not okay:
        return
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        try:
            _download(
                executor,
                http_client,
                uris_filenames,
                tmp_dirpath,
                chunk_size,
            )
        except KeyboardInterrupt:
            prepare_crash(executor)
            raise
    _check((filename for _, filename in uris_filenames), tmp_dirpath)
    tmp_dirpath.rename(output_dirpath)
    LOG.info('completed %s', output_dirpath)


def _prepare(output_dirpath):
    if output_dirpath.is_dir():
        LOG.warning('skip existing directory %s', output_dirpath)
        return False, None
    if output_dirpath.exists():
        raise DownloadError('not a directory %s' % output_dirpath)
    tmp_dirpath = output_dirpath.with_name(output_dirpath.name + '.part')
    if not tmp_dirpath.is_dir():
        if tmp_dirpath.exists():
            raise DownloadError('not a directory %s' % tmp_dirpath)
        tmp_dirpath.mkdir(parents=True)
    else:
        LOG.warning('resume from %s', tmp_dirpath)
    return True, tmp_dirpath


def _download(
        executor,
        http_client,
        uris_filenames,
        output_dirpath,
        chunk_size):
    futures = {}
    for uris, filename in uris_filenames:
        output_path = output_dirpath / filename
        if output_path.exists():
            LOG.warning('skip %s', output_path)
            continue
        futures[executor.submit(_get_one_of, http_client, uris)] = output_path
    for future in concurrent.futures.as_completed(futures):
        response = future.result()
        output_path = futures[future]
        tmp_output_path = output_path.with_name(output_path.name + '.part')
        with tmp_output_path.open('wb') as output:
            for chunk in response.iter_content(chunk_size):
                output.write(chunk)
        tmp_output_path.rename(output_path)
        LOG.info('downloaded %s', output_path)


def _check(filenames, output_dirpath):
    filenames = set(filenames)
    for filepath in output_dirpath.iterdir():
        if filepath.name not in filenames:
            LOG.warning('remove extra file %s', filepath)
            filepath.unlink()
        else:
            filenames.remove(filepath.name)
    if filenames:
        raise DownloadError('miss file(s) %r' % filenames)


def _get_one_of(http_client, uris):
    assert uris
    for uri in uris[:-1]:
        try:
            return http_client.get(uri)
        except requests.exceptions.HTTPError as exc:
            LOG.warning('uri=%s status_code=%d', uri, exc.response.status_code)
    return http_client.get(uris[-1])
