def clean(name):
    return name.strip()


def label(name):
    value = clean(name)
    return value.title()

