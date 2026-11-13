"""A failed completed native task remains distinguishable from a lost reply."""
from copy import deepcopy


class ManagedTaskFailure(RuntimeError):
    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt=deepcopy(receipt)
