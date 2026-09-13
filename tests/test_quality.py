from smallerer.model import Status
from smallerer.quality import assess


def test_empty():
    report = assess(["tiny"])
    assert report.status is Status.EMPTY


def test_low():
    report = assess(["A readable but short passage " * 4])
    assert report.status is Status.LOW


def test_ok():
    report = assess(["A normal searchable sentence with several words. " * 12])
    assert report.status is Status.OK


def test_replacement_characters_are_garbled():
    report = assess(["normal text " * 40 + "\ufffd" * 20])
    assert report.status is Status.GARBLED

