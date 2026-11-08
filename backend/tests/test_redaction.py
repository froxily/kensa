import pytest

from kensa.ingestion.redaction import redact

# Fake credentials built from pieces so this file never contains a scannable "real-looking" token.
GH_TOKEN = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
GH_PAT = "github_pat_" + "11ABCDEFG0" + "a" * 40
AWS_ID = "AKIA" + "IOSFODNN7EXAMPLE"
JWT = "eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0." + "dozjgNryP4J3jVmNHl0w5N"
NPM = "npm_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
SK = "sk-" + "proj-" + "Abcdefghij1234567890KLMNOPqrstu"


@pytest.mark.parametrize(
    ("text", "kind", "leak"),
    [
        (f"token={GH_TOKEN}", "github_token", GH_TOKEN),
        (f"Using {GH_PAT} for auth", "github_token", GH_PAT),
        (f"aws key {AWS_ID} loaded", "aws_key", AWS_ID),
        (f"Authorization: Bearer {JWT}", "bearer", JWT),
        (f"jwt {JWT}", "jwt", JWT),
        (f"//registry.npmjs.org/:_authToken {NPM}", "npm_token", NPM),
        (f"OPENAI_KEY {SK}", "api_key", SK),
        ("postgresql://app:s3cr3t-Passw0rd@db:5432/app", "password", "s3cr3t-Passw0rd"),
        ("DB_PASSWORD=hunter2hunter2", "secret", "hunter2hunter2"),
        ('client_secret: "x9Fq2LmZpQ"', "secret", "x9Fq2LmZpQ"),
        ("export API_KEY='kfj39DkslQ93'", "secret", "kfj39DkslQ93"),
        (
            "blob Zx9Qm2Lp8Rt5Vw3Yb7Nc4Hd6Jf1Kg0Ps2Tq9 end",
            "high_entropy",
            "Zx9Qm2Lp8Rt5Vw3Yb7Nc4Hd6Jf1Kg0Ps2Tq9",
        ),
    ],
)
def test_secrets_are_redacted(text: str, kind: str, leak: str) -> None:
    result = redact(text)
    assert leak not in result.text
    assert f"[REDACTED:{kind}]" in result.text
    assert result.counts.get(kind, 0) >= 1


@pytest.mark.parametrize(
    "text",
    [
        "HEAD is now at 3f1c9a7e2b4d6f8a0c1e3b5d7f9a1c3e5b7d9f1a fix build",
        "image sha256:9b2a7c1d3e5f7a9b1c3d5e7f9a1b3c5d7e9f1a3b5c7d9e1f3a5b7c9d1e3f5a7b",
        "integrity sha512-Zx9Qm2Lp8Rt5Vw3Yb7Nc4Hd6Jf1Kg0Ps2Tq9Ab3Cd5Ef7Gh9Ij1Kl3Mn5Op7",
        "run id 5f0c6e2a-8b1d-4c3e-9f7a-2d4b6c8e0a1f started",
        "Error: Missing required environment variable: VITE_API_BASE_URL",
        "Missing secret: API_TOKEN",
        "  token: ***",
        "DATABASE_URL: postgresql://app:***@localhost:5432/app_test",
        "file:///home/runner/work/storefront/storefront/scripts/check-env.mjs:9",
        "max_tokens=512 temperature=0",
        'password authentication failed for user "app"',
    ],
)
def test_evidence_is_not_redacted(text: str) -> None:
    result = redact(text)
    assert result.text == text
    assert result.total == 0


PK = "PRIVATE " + "KEY-----"  # split so secret scanners don't flag these fake fixtures


def test_private_key_block_keeps_line_count() -> None:
    text = (
        f"before\n-----BEGIN RSA {PK}\nMIIEowIBAAKCAQEAsQ2abcdefghijklmnop\n"
        f"qrstuvwxyz0123456789ABCDEFGHIJKL\n-----END RSA {PK}\nafter"
    )
    result = redact(text)
    assert "MIIEowIBAAKCAQEA" not in result.text
    assert result.text.count("\n") == text.count("\n")
    assert result.text.splitlines()[0] == "before"
    assert result.text.splitlines()[-1] == "after"


def test_unterminated_private_key_is_redacted() -> None:
    text = f"-----BEGIN OPENSSH {PK}\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAE\nnext line"
    result = redact(text)
    assert "b3BlbnNzaC1rZXkt" not in result.text
    assert result.text.count("\n") == text.count("\n")


def test_redaction_is_idempotent_and_line_preserving() -> None:
    text = "\n".join([f"token={GH_TOKEN}", "plain", "DB_PASSWORD=hunter2hunter2", "end"])
    once = redact(text)
    twice = redact(once.text)
    assert twice.text == once.text
    assert twice.total == 0
    assert once.text.count("\n") == text.count("\n")
