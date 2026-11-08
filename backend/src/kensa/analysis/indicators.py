"""Deterministic text indicators used by the completeness check and the diagnosis verifier (M3).

* ``CATEGORY_INDICATORS``: vocabulary that a line must show before it can support a diagnosis of
  that category. Written from the category definitions, deliberately broad: they exist to catch
  a claim that none of its citations is about (for example "test regression" backed only by an
  exit-code line), not to classify.
* ``FAILURE_MARKER``: any sign that something failed. Generous on purpose: a false "no failure
  shown" makes Kensa abstain on a real failure, so only logs with no failure vocabulary at all
  count as not showing one.
* ``TRUNCATION_MARKER``: the log says it is incomplete.
* ``INSTRUCTION_LIKE``: text addressed to an AI model (prompt injection). Such lines are data;
  they can never serve as evidence.
"""

import re

from kensa.analysis.categories import Category


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


CATEGORY_INDICATORS: dict[Category, re.Pattern[str]] = {
    "missing_env_var": _p(
        r"\benv(?:ironment)?\b|variable|secret|\bnot set\b|\bunset\b|undefined|not defined"
        r"|\bis required\b|\bmissing\b|KeyError|process\.env|os\.environ|getenv"
        r"|\$\{\{\s*(?:secrets|vars|env)\."
    ),
    "dependency_build": _p(
        r"depend|resol(?:v|ution)|install|lock ?file|lockfile|-lock\.|package|module|import"
        r"|version|requir|compil|\bbuild|wheel|\bnpm\b|pnpm|yarn|\bpip\b|poetry|cargo|maven"
        r"|gradle|go\.(?:mod|sum)|bundler?|gem|registry|peer|ERESOLVE|syntax ?error"
        r"|undefined reference|error TS\d|\btsc\b|linker|cannot find (?:module|package|symbol)"
    ),
    "github_permissions": _p(
        r"permission|forbidden|\b40[13]\b|denied|not accessible|unauthori[sz]ed|GITHUB_TOKEN"
        r"|\btoken\b|\bscopes?\b|credential|write access|read-only"
    ),
    "db_connectivity": _p(
        r"database|\bdb\b|postgres|\bpsql\b|\bpg\b|mysql|mariadb|mongo|redis|sqlite|\bsql"
        r"|connection (?:refused|reset|timed out)|could not connect|can't connect|ECONNREFUSED"
        r"|ENOTFOUND|getaddrinfo|OperationalError|Communications link|authentication failed"
        r"|server running|accepting (?:tcp/ip )?connections|:5432\b|:3306\b|:6379\b|:27017\b"
    ),
    "docker": _p(
        r"docker|container|\bimage\b|registry|\bpull\b|manifest|daemon|buildx|compose|ghcr\.io"
        r"|\boci\b|podman"
    ),
    "workflow_path": _p(
        r"no such file|not found|does not exist|ENOENT|\bpath\b|director(?:y|ies)"
        r"|working-directory|can't find|cannot find|unable to resolve action|no files were found"
        r"|action\.ya?ml|\.github/"
    ),
    "test_regression": _p(
        r"\btests?\b|assert|expect(?:ed|s)?\b|\bFAILED\b|--- FAIL|✕|✗|\bnot ok\b|\bspecs?\b"
        r"|snapshot|pytest|jest|vitest|mocha|junit|rspec|\bTests run:|# fail [1-9]"
    ),
    "oom_timeout": _p(
        r"memory|\bOOM\b|killed|\b137\b|heap|ENOMEM|no space left|\bdisk\b|time(?:d)? ?out"
        r"|exceeded|cancel(?:l)?ed|maximum execution time|deadline"
    ),
}

FAILURE_MARKER = _p(
    r"##\[error\]|\berrors?\b|\bfail(?:ed|ure|ures|ing|s)?\b|\bfatal\b|exception|traceback"
    r"|\bpanic\b|segmentation fault|\bkilled\b|denied|refused|forbidden|timed? ?out"
    r"|\bcannot\b|can't|could not|unable to|not found|no such file|does not exist|ERR!"
    r"|exit (?:code|status) [1-9]|exited with (?:code )?[1-9]|\bE[A-Z0-9_]{3,}\b:"
)

TRUNCATION_MARKER = _p(
    r"\btruncated\b|remaining output (?:is )?unavailable|output (?:was )?cut off"
    r"|log (?:stream )?(?:was )?interrupted|\(\d+ (?:more )?lines? (?:omitted|hidden)\)"
)

INSTRUCTION_LIKE = _p(
    r"\b(?:ignore|disregard|forget|override)\b.{0,40}\b(?:instructions?|prompts?|rules)\b"
    r"|\byou are (?:now )?(?:an?|the) (?:ai|assistant|language model|llm|model)\b"
    r"|\bsystem prompt\b|<\|?(?:system|assistant|im_start|im_end)\|?>"
    r"|\b(?:mark|report|classify|label)\b.{0,40}\b(?:as )?(?:verified|category)\b.{0,40}"
    r"\b(?:instead|regardless|always)\b"
    r"|\b(?:respond|reply|answer) (?:only )?with\b.{0,40}\bjson\b"
)


def supports_category(text: str, category: Category) -> bool:
    pattern = CATEGORY_INDICATORS.get(category)
    return pattern is not None and pattern.search(text) is not None


def is_instruction_like(text: str) -> bool:
    return INSTRUCTION_LIKE.search(text) is not None
