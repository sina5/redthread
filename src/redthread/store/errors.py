"""StoreError lives in its own module so both local.py and gitio.py can
import it without a circular dependency between them."""


class StoreError(Exception):
    pass
