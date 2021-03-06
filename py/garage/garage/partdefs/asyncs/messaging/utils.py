from garage import parameters
from garage import parts
from garage.partdefs.asyncs.messaging import reqrep


def create_parts(module_name=None):
    part_list = parts.Parts(module_name)
    part_list.client = parts.AUTO
    part_list.conn = reqrep.create_client_parts()
    return part_list


def create_params(*, packed=False, **reqrep_params):
    params = parameters.create_namespace('create service client')
    params.conn = reqrep.create_client_params(**reqrep_params)
    params.packed = parameters.create(packed, 'use packed format')
    return params


def create_makers(part_list, params, *, client_class):
    def make_client(
            request_queue: part_list.conn.request_queue,
        ) -> part_list.client:
        return client_class(request_queue, packed=params.packed.get())
    return [
        make_client,
        reqrep.create_client_maker(part_list.conn, params.conn),
    ]
