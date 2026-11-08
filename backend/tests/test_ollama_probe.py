import httpx
import pytest
import respx

from kensa.inference.ollama import normalize_model_name, probe_ollama

BASE = "http://127.0.0.1:11434"
MODEL = "qwen3:4b-instruct-2507-q4_K_M"


def _tags(*names: str) -> httpx.Response:
    return httpx.Response(200, json={"models": [{"name": n, "size": 1} for n in names]})


def test_ok_when_model_present(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE}/api/tags").mock(return_value=_tags("other:1b", MODEL))
    status = probe_ollama(BASE, MODEL, 1.0)
    assert status.status == "ok"
    assert status.detail is None


def test_model_missing(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE}/api/tags").mock(return_value=_tags("other:1b"))
    assert probe_ollama(BASE, MODEL, 1.0).status == "model_missing"


def test_empty_model_list_is_model_missing(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE}/api/tags").mock(return_value=httpx.Response(200, json={}))
    assert probe_ollama(BASE, MODEL, 1.0).status == "model_missing"


def test_untagged_name_matches_latest(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE}/api/tags").mock(return_value=_tags("tiny:latest"))
    assert probe_ollama(BASE, "tiny", 1.0).status == "ok"


@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (httpx.ConnectError("refused"), "connection_failed"),
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectTimeout("slow"), "timeout"),
    ],
)
def test_transport_failures_are_unavailable(
    respx_mock: respx.MockRouter, error: Exception, detail: str
) -> None:
    respx_mock.get(f"{BASE}/api/tags").mock(side_effect=error)
    status = probe_ollama(BASE, MODEL, 1.0)
    assert (status.status, status.detail) == ("unavailable", detail)


def test_http_error_status(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE}/api/tags").mock(return_value=httpx.Response(500))
    status = probe_ollama(BASE, MODEL, 1.0)
    assert (status.status, status.detail) == ("error", "http_500")


def test_redirects_are_not_followed(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE}/api/tags").mock(
        return_value=httpx.Response(302, headers={"Location": "http://evil.example/api/tags"})
    )
    status = probe_ollama(BASE, MODEL, 1.0)
    assert (status.status, status.detail) == ("error", "http_302")


@pytest.mark.parametrize("body", [b"not json", b'{"models": "nope"}', b'{"models": [{"x": 1}]}'])
def test_malformed_response(respx_mock: respx.MockRouter, body: bytes) -> None:
    respx_mock.get(f"{BASE}/api/tags").mock(return_value=httpx.Response(200, content=body))
    status = probe_ollama(BASE, MODEL, 1.0)
    assert (status.status, status.detail) == ("error", "malformed_response")


@pytest.mark.parametrize(
    ("name", "expected"),
    [("qwen3", "qwen3:latest"), ("qwen3:4b", "qwen3:4b"), ("a/b:c", "a/b:c")],
)
def test_normalize_model_name(name: str, expected: str) -> None:
    assert normalize_model_name(name) == expected
