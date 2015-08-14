"""Helper functions, etc."""

__all__ = [
    'form',
]


def form(client, uri, *,
         form_xpath='//form',
         form_data=None,
         encoding=None,
         kwargs=None):
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
