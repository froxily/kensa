import responses
import requests

@responses.activate
def test_feed_is_read():
    responses.add(
        responses.GET,
        "https://feed.invalid/items",
        json={"items": ["reed"]},
        status=200,
    )
    assert requests.get("https://feed.invalid/items").json()["items"] == ["reed"]
