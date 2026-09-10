from urllib.parse import quote

import requests

from app.config import settings


class WikipediaService:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.timeout = 15
        self.verify = settings.internet_ssl_verify
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "movie-review-agent-system/1.0",
        }

    def fetch_movie_summary(self, movie_title: str) -> dict | None:
        search_results = self._search(movie_title=movie_title)
        if not search_results:
            return None

        selected = self._select_result(movie_title=movie_title, results=search_results)
        page_title = selected.get("title")
        if not page_title:
            return None

        summary = self._summary(page_title=page_title)
        if not summary:
            return None

        return {
            "source": "Wikipedia",
            "page_title": summary.get("title") or page_title,
            "description": summary.get("description") or selected.get("description"),
            "extract": summary.get("extract"),
            "url": ((summary.get("content_urls") or {}).get("desktop") or {}).get("page"),
            "thumbnail": (summary.get("thumbnail") or {}).get("source"),
        }

    def _search(self, movie_title: str) -> list[dict]:
        response = self.session.get(
            "https://en.wikipedia.org/w/rest.php/v1/search/page",
            params={"q": f"{movie_title} film", "limit": 3},
            headers=self.headers,
            timeout=self.timeout,
            verify=self.verify,
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("pages", [])

    def _summary(self, page_title: str) -> dict:
        response = self.session.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(page_title, safe='')}",
            headers=self.headers,
            timeout=self.timeout,
            verify=self.verify,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _select_result(movie_title: str, results: list[dict]) -> dict:
        normalized_title = movie_title.lower()

        def score(result: dict) -> int:
            title = str(result.get("title") or "").lower()
            description = str(result.get("description") or "").lower()
            value = 0
            if normalized_title in title:
                value += 2
            if "film" in description or "movie" in description:
                value += 1
            return value

        return sorted(results, key=score, reverse=True)[0]
