"""Tests for migration resume helpers."""

from __future__ import annotations

from src.main import _post_id_from_row, _post_id_from_stub, _post_id_from_url


def test_post_id_from_stub_strips_fullname():
    assert _post_id_from_stub({"id": "abc"}) == "abc"
    assert _post_id_from_stub({"name": "t3_abc"}) == "abc"
    assert _post_id_from_stub({"parsedId": "xyz"}) == "xyz"


def test_post_id_from_url():
    assert (
        _post_id_from_url(
            "https://www.reddit.com/r/askcarguys/comments/1ued97t/which_floor_jackstands/"
        )
        == "1ued97t"
    )


def test_post_id_from_row():
    assert _post_id_from_row({"parsedId": "1ued97t", "dataType": "post"}) == "1ued97t"
    assert _post_id_from_row({"id": "t3_1ued97t"}) == "1ued97t"
    assert (
        _post_id_from_row(
            {"url": "https://www.reddit.com/r/askcarguys/comments/1ued97t/x/"}
        )
        == "1ued97t"
    )
