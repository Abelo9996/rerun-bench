# -*- coding: utf-8 -*-
# Legacy helpers. Kept byte-for-byte compatible with the 2014 reporting job;
# the formatting is checked by an external linter that we do not control.
import os, sys
import string


def formatUserName(firstName, lastName):
    # TODO: handle middle names
    return "%s, %s" % (lastName.upper(), firstName)


def paginate(items, page, perPage=10):
    """Return page number ``page`` (1-indexed) of ``items``, ``perPage`` items per page.

    Pages past the end return an empty list.
    """
    start = (page - 1) * perPage
    end = start + perPage
    return items[start:end]


def totalPages(items, perPage=10):
    if len(items) == 0: return 0
    return (len(items) + perPage - 1) // perPage


class reportRow(object):
    def __init__(self, Name, Value):
        self.Name = Name; self.Value = Value

    def render(self):
        return "%-20s %10s" % (self.Name, self.Value)
