import pytest
from pydantic import ValidationError

from kensa.core.config import Settings


def test_defaults_are_local_only() -> None:
    settings = Settings(_env_file=None)
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.inference_provider == "ollama"
    assert settings.llm_model == "qwen3:4b-instruct-2507-q4_K_M"
    assert settings.llm_num_ctx == 8192
    assert settings.llm_num_gpu == 99


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://localhost:11434", "http://localhost:11434"),
        ("http://[::1]:11434", "http://[::1]:11434"),
        ("http://127.0.0.1:11434/", "http://127.0.0.1:11434"),
    ],
)
def test_loopback_ollama_urls_are_accepted(url: str, expected: str) -> None:
    assert Settings(_env_file=None, ollama_base_url=url).ollama_base_url == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://0.0.0.0:11434",
        "http://192.168.1.5:11434",
        "http://ollama.example.com",
        "ftp://127.0.0.1:11434",
        "http://user:pw@127.0.0.1:11434",
        "not a url",
    ],
)
def test_non_local_ollama_urls_are_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_base_url=url)


@pytest.mark.parametrize("num_ctx", [0, 511, 32769])
def test_num_ctx_is_bounded(num_ctx: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_num_ctx=num_ctx)


def test_database_password_is_not_in_repr() -> None:
    settings = Settings(
        _env_file=None, database_url="postgresql+psycopg://u:hunter2@127.0.0.1:5433/db"
    )
    assert "hunter2" not in repr(settings)
    assert "hunter2" not in str(settings.model_dump())


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_github_token_means_anonymous_access(value: str) -> None:
    assert Settings(_env_file=None, github_token=value).github_token is None


def test_a_github_token_is_kept_secret() -> None:
    fake = " github_pat_" + "secret123 "
    settings = Settings(_env_file=None, github_token=fake)
    assert settings.github_token is not None
    assert settings.github_token.get_secret_value() == "github_pat_secret123"
    assert "secret123" not in repr(settings)
