from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Look up a dict value by a variable key: {{ my_dict|get_item:variable_key }}"""
    if dictionary is None:
        return None
    try:
        return dictionary.get(key) or dictionary.get(int(key))
    except (TypeError, ValueError):
        return dictionary.get(key)
