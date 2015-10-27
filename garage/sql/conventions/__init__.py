"""Conventions for preparing REFS context."""

__all__ = [
    'prepare_model_context',
    'make_junction_table_short_name',
]

from garage import asserts


def prepare_model_context(context, models, junction_models, make_table_name):
    for model in models:
        context[model.name] = model

        short_name = model.a.sql.short_name
        asserts.precond(short_name)
        context[short_name] = make_table_name(short_name)

    for junction_model in junction_models:
        short_name = make_junction_table_short_name(junction_model)
        context[short_name] = make_table_name(short_name)


def make_junction_table_short_name(junction_models):
    return '_'.join(model.a.sql.short_name for model in junction_models)
