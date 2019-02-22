"""Demonstrate ``g1.http.spiders``."""

import urllib.parse

from startup import startup

from g1.apps import asyncs
from g1.asyncs import kernels
from g1.http import spiders

import g1.asyncs.servers.parts
import g1.http.spiders.parts

LABELS = g1.http.spiders.parts.define_spider()


class Controller(spiders.Controller):

    def __init__(self, url_base):
        self._url_base = url_base
        self._urls = set()

    async def on_crawl_start(self, spider):
        spider.enqueue(self._url_base, 0)
        self._urls.add(self._url_base)

    async def on_response(self, spider, serial, request, response):
        print(request.url)
        content_type = response.headers.get('content-type', '')
        if content_type.lower().startswith('text/html'):
            for link in response.html().xpath('//a'):
                url = urllib.parse.urljoin(request.url, link.get('href'))
                url = urllib.parse.urldefrag(url).url
                if url.startswith(self._url_base) and url not in self._urls:
                    spider.enqueue(url, 0)
                    self._urls.add(url)


@startup
def add_arguments(parser: asyncs.LABELS.parser) -> asyncs.LABELS.parse:
    parser.add_argument('url_base')


@startup
def make_controller(args: asyncs.LABELS.args) -> LABELS.controller:
    return Controller(args.url_base)


def main(supervise_servers: g1.asyncs.servers.parts.LABELS.supervise_servers):
    kernels.run(supervise_servers)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
