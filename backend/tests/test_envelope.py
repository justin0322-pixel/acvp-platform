import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.models.envelope import wrap, unwrap


def test_wrap_shape():
    env = wrap({"hello": "world"})
    assert isinstance(env, list) and len(env) == 2
    assert env[0] == {"acvVersion": get_settings().acv_version}
    assert env[1] == {"hello": "world"}


def test_unwrap_roundtrip():
    assert unwrap(wrap({"a": 1})) == {"a": 1}


def test_unwrap_rejects_bad_version():
    with pytest.raises(HTTPException):
        unwrap([{"acvVersion": "9.9"}, {}])


def test_unwrap_rejects_malformed():
    with pytest.raises(HTTPException):
        unwrap({"not": "a list"})
