import json
import os
import sys
import warnings
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest


@pytest.mark.parametrize("name", ["a", "b", "c", "d", "e", "f", "g", "h", "i"])
def test_slug(name):
    warnings.warn("legacy slug helper is deprecated", DeprecationWarning)
    assert name.strip() == name


def test_post_comment():
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GH_TOKEN"]
    request = Request(
        f"https://api.github.com/repos/{repo}/issues/12/comments",
        data=json.dumps({"body": "Integration check"}).encode(),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request) as response:
            assert response.status == 201
    except HTTPError as exc:
        print(exc.read().decode(), file=sys.stderr)
        raise
