"""
Helper classes and functions for sync-prof

TODO:
- exception with stack trace printing
- logging
"""


import logging


# TODO: exception handling
# TODO: refactor sp_model to use SPStack
class SPStack(object):
    "simple LIFO"
    def __init__(self):
        self.stack = []
    def push(self, lmn):
        "push to stack"
        self.stack += [lmn]
    def top(self):
        "return top of the stack"
        assert not self.empty(), 'stack empty'
        return self.stack[-1]
    def pop(self):
        "pop the top of the stack"
        lmn = self.top()
        self.stack = self.stack[:-1]
        return lmn
    def size(self):
        "return number of elements in stack"
        return len(self.stack)
    def empty(self):
        "True if stack is empty"
        return self.stack == []
    def __iter__(self):
        "iterator over stack elements, top element first"
        for lmn in self.stack[::-1]:
            yield lmn


def setupLogging(logLevel):
    "return a logger"
    log = logging.getLogger('sync-prof')
    log.setLevel(logLevel)
    h = logging.StreamHandler()
    formatter = logging.Formatter('%(name)s: %(levelname)s: %(message)s')
    h.setFormatter(formatter)
    log.addHandler(h)
    return log
