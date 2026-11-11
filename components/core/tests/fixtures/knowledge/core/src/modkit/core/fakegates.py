"""A tiny stand-in for a component's gates, resolved by the knowledge check."""


def check_names(value):
    return value


class NameShape:
    def accepts(self, value):
        return bool(value)


SHAPE_TABLE = {}
