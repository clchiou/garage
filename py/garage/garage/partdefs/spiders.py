from garage import parameters
from garage import parts
from garage import spiders
from garage.partdefs.http import clients


PARTS = parts.PartList(spiders.__name__, [
    ('parser', parts.AUTO),
    ('spider', parts.AUTO),
])


PARAMS = parameters.get(
    spiders.__name__, 'web spider framework')
PARAMS.num_spiders = parameters.define(
    8, 'set number of spider threads')


@parts.register_maker
def make_spider(
        client: clients.PARTS.client, parser: PARTS.parser) -> PARTS.spider:
    return spiders.Spider(
        num_spiders=PARAMS.num_spiders.get(),
        client=client,
        parser=parser,
    )
