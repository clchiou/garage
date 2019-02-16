from g1.apps import labels
from g1.apps import parameters
from g1.apps import utils
from g1.http import spiders

import g1.asyncs.servers.parts


def define_spider(module_path=None, *, session_label=None, **kwargs):
    """Define a spider object under ``module_path``."""

    module_path = module_path or spiders.__name__

    module_labels = labels.make_labels(
        module_path,
        'spider_params',
        'spider',
        'controller',
    )

    utils.depend_parameter_for(
        module_labels.spider_params,
        parameters.define(
            module_path,
            make_spider_params(**kwargs),
        ),
    )

    annotations = {
        'params': module_labels.spider_params,
        'controller': module_labels.controller,
        'return': module_labels.spider,
    }
    if session_label:
        annotations['session'] = session_label
    utils.define_maker(make_spider, annotations)

    utils.define_maker(
        lambda spider: spider.crawl,
        {
            'spider': module_labels.spider,
            'return': g1.asyncs.servers.parts.LABELS.serve,
        },
    )

    utils.define_binder(
        on_graceful_exit,
        g1.asyncs.servers.parts.LABELS.serve,
        {
            'spider': module_labels.spider,
        },
    )

    return module_labels


async def on_graceful_exit(
    graceful_exit: g1.asyncs.servers.parts.LABELS.graceful_exit,
    spider,
):
    await graceful_exit.wait()
    spider.request_shutdown()


def make_spider_params(
    check_request_id=True,
    max_num_tasks=0,
):
    return parameters.Namespace(
        'make HTTP spider',
        check_request_id=parameters.Parameter(check_request_id),
        max_num_tasks=parameters.Parameter(max_num_tasks),
    )


def make_spider(params, controller, session=None):
    return spiders.Spider(
        controller,
        session=session,
        check_request_id=params.check_request_id.get(),
        max_num_tasks=params.max_num_tasks.get(),
    )
