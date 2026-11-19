"""Publish compile drafts with zero or one new inbox source via the shared writer."""

from .save import _publish_draft


def compile(draft, confirm=None):
    return _publish_draft(draft, confirm, 'compile')
