from garage import parameters
from garage import parts
from garage import spiders
from garage.partdefs.http import clients


PARTS = parts.Parts(spiders.__name__)
PARTS.parser = parts.AUTO
PARTS.spider = parts.AUTO


PARAMS = parameters.define_namespace(
    spiders.__name__, 'web spider framework')
PARAMS.num_spiders = parameters.create(
    8, 'set number of spider threads')


@parts.define_maker
def make_spider(
        client: clients.PARTS.client, parser: PARTS.parser) -> PARTS.spider:
    return spiders.Spider(
        num_spiders=PARAMS.num_spiders.get(),
        client=client,
        parser=parser,
    )
