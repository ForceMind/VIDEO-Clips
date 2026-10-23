"""Search Openverse's public audio index; preserve per-asset licenses/attribution."""
from __future__ import annotations
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API = "https://api.openverse.org/v1/audio/"
ALLOWED_COMMERCIAL = {"cc0", "by", "by-sa", "pdm", "publicdomain", "cc-by", "cc-by-sa"}


def search_audio(term: str, *, limit: int = 10, commercial: bool = False, timeout: int = 20) -> list[dict]:
    if not term.strip() or len(term) > 120:
        raise ValueError("query must contain 1..120 characters")
    if not 1 <= limit <= 20:
        raise ValueError("limit must be 1..20")
    query = urlencode({"q": term, "page_size": min(limit * 3, 50)})
    request = Request(API + "?" + query, headers={"User-Agent": "VIDEO-Clips/0.1 (metadata-only)",
                                                    "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    results = []
    for asset in payload.get("results", []):
        license_id = str(asset.get("license", "")).lower()
        if commercial and license_id not in ALLOWED_COMMERCIAL:
            continue
        results.append({"title": asset.get("title"), "license": license_id,
                        "license_version": asset.get("license_version"),
                        "creator": asset.get("creator"), "creator_url": asset.get("creator_url"),
                        "attribution": asset.get("attribution"),
                        "url": asset.get("url"), "foreign_landing_url": asset.get("foreign_landing_url"),
                        "duration": asset.get("duration"), "id": asset.get("id")})
        if len(results) >= limit:
            break
    return results
