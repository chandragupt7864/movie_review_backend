from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
import socket
import time

import certifi
import requests
import urllib3
import urllib3.util.connection
from requests.adapters import HTTPAdapter
from requests.exceptions import ConnectionError, RequestException, SSLError, Timeout
from urllib3.util.retry import Retry

from app.config import settings
from app.constants import (
    ALLOWED_GENRE_IDS,
    HOLLYWOOD_LANGUAGE,
    HOLLYWOOD_ORIGINAL_LANGUAGE,
    TMDB_BASE_URL,
    TMDB_IMAGE_BASE_URL,
)

MOVIE_CATEGORIES = {
    "all": {"label": "All Movies", "source": "discover"},
    "popular": {"label": "Popular", "source": "popular"},
    "now_playing": {"label": "Now Playing", "source": "now_playing"},
    "upcoming": {"label": "Upcoming", "source": "upcoming"},
    "top_rated": {"label": "Top Rated", "source": "top_rated"},
    "trending_day": {"label": "Trending Today", "source": "trending_day"},
    "trending_week": {"label": "Trending This Week", "source": "trending_week"},
}

SUPPORTED_SORT_OPTIONS = {
    "popularity.desc",
    "popularity.asc",
    "primary_release_date.desc",
    "primary_release_date.asc",
    "vote_average.desc",
    "vote_average.asc",
    "vote_count.desc",
    "vote_count.asc",
    "revenue.desc",
    "revenue.asc",
    "original_title.asc",
    "original_title.desc",
}


class TMDBService:
    _config_cache: dict[str, tuple[float, object]] = {}

    def __init__(self) -> None:
        if not settings.tmdb_api_key and not settings.tmdb_bearer_token:
            raise ValueError("TMDB_API_KEY or TMDB_BEARER_TOKEN is not configured.")
        self.base_url = TMDB_BASE_URL
        self.verify = settings.tmdb_ca_bundle or certifi.where()
        if not settings.tmdb_ssl_verify:
            self.verify = False
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.timeout = settings.tmdb_timeout_seconds
        if settings.tmdb_force_ipv4:
            urllib3.util.connection.allowed_gai_family = lambda: socket.AF_INET
        self.headers = {
            "Accept": "application/json",
            "Connection": "close",
            "User-Agent": "movie-review-agent-system/1.0",
        }
        if settings.tmdb_bearer_token and not settings.tmdb_api_key:
            self.headers["Authorization"] = f"Bearer {settings.tmdb_bearer_token}"
        self.session = self._build_session()

    @staticmethod
    def _build_session() -> requests.Session:
        session = requests.Session()
        session.trust_env = settings.tmdb_use_env_proxy
        retry = Retry(
            total=settings.tmdb_retry_count,
            connect=0,
            read=0,
            other=0,
            status=settings.tmdb_retry_count,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def fetch_movies(self, category: str, page: int) -> list[dict]:
        if category == "trending":
            return self._fetch_trending(page=page)
        if category == "upcoming":
            return self._fetch_upcoming(page=page)
        return self._fetch_discover(category=category, page=page)

    def fetch_movie_videos(self, tmdb_id: int) -> dict:
        return self._get(
            endpoint=f"/movie/{tmdb_id}/videos",
            params={"language": HOLLYWOOD_LANGUAGE},
        )

    def get_movie_details(self, tmdb_id: int) -> dict:
        return self._get(
            endpoint=f"/movie/{tmdb_id}",
            params={
                "language": HOLLYWOOD_LANGUAGE,
                "append_to_response": "credits,keywords,external_ids",
            },
        )

    def get_movie_reviews(self, tmdb_id: int) -> dict:
        return self._get(
            endpoint=f"/movie/{tmdb_id}/reviews",
            params={"language": HOLLYWOOD_LANGUAGE, "page": 1},
        )

    def browse_movies_general(
        self,
        *,
        query: str | None,
        category: str,
        genre_id: int | None,
        language: str | None,
        original_language: str | None,
        region: str | None,
        year: int | None,
        month: int | None,
        date_from: str | None,
        date_to: str | None,
        sort_by: str,
        vote_average_min: float | None,
        vote_count_min: int | None,
        include_adult: bool,
        page: int,
    ) -> dict:
        effective_language = (language or HOLLYWOOD_LANGUAGE).strip() or HOLLYWOOD_LANGUAGE
        normalized_date_from, normalized_date_to = self.resolve_date_range(
            year=year,
            month=month,
            date_from=date_from,
            date_to=date_to,
        )
        genre_map = self.get_movie_genre_map(language=effective_language)
        if genre_id is not None and genre_id not in genre_map:
            raise LookupError("Invalid movie genre")
        if category not in MOVIE_CATEGORIES:
            raise LookupError("Invalid category")
        if sort_by not in SUPPORTED_SORT_OPTIONS:
            raise LookupError("Invalid sort_by value")

        if query:
            payload = self.search_movies_general(
                query=query,
                page=page,
                language=effective_language,
                include_adult=include_adult,
                genre_id=genre_id,
                original_language=original_language,
                region=region,
                date_from=normalized_date_from,
                date_to=normalized_date_to,
                vote_average_min=vote_average_min,
                vote_count_min=vote_count_min,
                sort_by=sort_by,
            )
        else:
            payload = self.discover_movies_general(
                category=category,
                page=page,
                language=effective_language,
                include_adult=include_adult,
                genre_id=genre_id,
                original_language=original_language,
                region=region,
                date_from=normalized_date_from,
                date_to=normalized_date_to,
                vote_average_min=vote_average_min,
                vote_count_min=vote_count_min,
                sort_by=sort_by,
            )

        payload["genre_map"] = genre_map
        payload["effective_date_from"] = normalized_date_from
        payload["effective_date_to"] = normalized_date_to
        payload["effective_language"] = effective_language
        return payload

    def search_movies_general(
        self,
        *,
        query: str,
        page: int,
        language: str,
        include_adult: bool,
        genre_id: int | None,
        original_language: str | None,
        region: str | None,
        date_from: str | None,
        date_to: str | None,
        vote_average_min: float | None,
        vote_count_min: int | None,
        sort_by: str,
    ) -> dict:
        payload = self._get(
            endpoint="/search/movie",
            params={
                "query": query,
                "include_adult": str(include_adult).lower(),
                "language": language,
                "page": page,
                **({"region": region} if region else {}),
            },
        )
        results = self._filter_general_results(
            results=list(payload.get("results") or []),
            genre_id=genre_id,
            original_language=original_language,
            date_from=date_from,
            date_to=date_to,
            include_adult=include_adult,
            vote_average_min=vote_average_min,
            vote_count_min=vote_count_min,
        )
        results = self._sort_results_locally(results=results, sort_by=sort_by)
        return {
            "page": int(payload.get("page") or page),
            "total_pages": int(payload.get("total_pages") or 1),
            "total_results": int(payload.get("total_results") or len(results)),
            "results": results,
        }

    def discover_movies_general(
        self,
        *,
        category: str,
        page: int,
        language: str,
        include_adult: bool,
        genre_id: int | None,
        original_language: str | None,
        region: str | None,
        date_from: str | None,
        date_to: str | None,
        vote_average_min: float | None,
        vote_count_min: int | None,
        sort_by: str,
    ) -> dict:
        category_source = MOVIE_CATEGORIES[category]["source"]
        if category_source == "discover":
            return self._discover_general(
                page=page,
                language=language,
                include_adult=include_adult,
                genre_id=genre_id,
                original_language=original_language,
                region=region,
                date_from=date_from,
                date_to=date_to,
                vote_average_min=vote_average_min,
                vote_count_min=vote_count_min,
                sort_by=sort_by,
            )

        endpoint_map = {
            "popular": "/movie/popular",
            "now_playing": "/movie/now_playing",
            "upcoming": "/movie/upcoming",
            "top_rated": "/movie/top_rated",
            "trending_day": "/trending/movie/day",
            "trending_week": "/trending/movie/week",
        }
        endpoint = endpoint_map[category_source]
        params = {"language": language, "page": page}
        if region and category_source in {"popular", "now_playing", "upcoming", "top_rated"}:
            params["region"] = region
        payload = self._get(endpoint=endpoint, params=params)
        results = self._filter_general_results(
            results=list(payload.get("results") or []),
            genre_id=genre_id,
            original_language=original_language,
            date_from=date_from,
            date_to=date_to,
            include_adult=include_adult,
            vote_average_min=vote_average_min,
            vote_count_min=vote_count_min,
        )
        results = self._sort_results_locally(results=results, sort_by=sort_by)
        return {
            "page": int(payload.get("page") or page),
            "total_pages": int(payload.get("total_pages") or 1),
            "total_results": int(payload.get("total_results") or len(results)),
            "results": results,
        }

    def get_movie_categories(self) -> list[dict]:
        return [{"value": value, "label": config["label"]} for value, config in MOVIE_CATEGORIES.items()]

    def get_all_movie_genres(self, language: str = HOLLYWOOD_LANGUAGE) -> list[dict]:
        cache_key = f"genres:{language}"
        cached = self._get_cached_config(cache_key)
        if cached is not None:
            return cached
        payload = self._get(endpoint="/genre/movie/list", params={"language": language})
        genres = list(payload.get("genres") or [])
        genres = sorted(
            [
                {"id": int(item["id"]), "name": str(item["name"])}
                for item in genres
                if item.get("id") is not None and item.get("name")
            ],
            key=lambda item: item["name"].lower(),
        )
        self._set_cached_config(cache_key, genres)
        return genres

    def get_movie_genre_map(self, language: str = HOLLYWOOD_LANGUAGE) -> dict[int, str]:
        return {item["id"]: item["name"] for item in self.get_all_movie_genres(language=language)}

    def get_available_languages(self) -> list[dict]:
        cache_key = "languages"
        cached = self._get_cached_config(cache_key)
        if cached is not None:
            return cached
        payload = self._get(endpoint="/configuration/languages", params={})
        languages = sorted(
            [
                {
                    "iso_639_1": str(item.get("iso_639_1") or ""),
                    "english_name": str(item.get("english_name") or ""),
                    "name": str(item.get("name") or ""),
                }
                for item in payload or []
                if item.get("iso_639_1")
            ],
            key=lambda item: item["english_name"].lower(),
        )
        self._set_cached_config(cache_key, languages)
        return languages

    def get_available_regions(self) -> list[dict]:
        cache_key = "regions"
        cached = self._get_cached_config(cache_key)
        if cached is not None:
            return cached
        payload = self._get(endpoint="/configuration/countries", params={})
        regions = sorted(
            [
                {
                    "iso_3166_1": str(item.get("iso_3166_1") or ""),
                    "english_name": str(item.get("english_name") or ""),
                    "native_name": str(item.get("native_name") or item.get("english_name") or ""),
                }
                for item in payload or []
                if item.get("iso_3166_1")
            ],
            key=lambda item: item["english_name"].lower(),
        )
        self._set_cached_config(cache_key, regions)
        return regions

    def get_movie_details_for_selector(self, tmdb_id: int, language: str = HOLLYWOOD_LANGUAGE) -> dict:
        details = self._get(
            endpoint=f"/movie/{tmdb_id}",
            params={
                "language": language,
                "append_to_response": "external_ids",
            },
        )
        return details

    def search_movies(
        self,
        *,
        query: str | None,
        category: str,
        page: int,
        genre_ids: list[int] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> dict:
        genre_filter = genre_ids or list(ALLOWED_GENRE_IDS.keys())
        category_value = category if category in {"released", "upcoming", "trending"} else "released"

        if query:
            params = {
                "query": query,
                "include_adult": "false",
                "language": HOLLYWOOD_LANGUAGE,
                "page": page,
                "region": settings.tmdb_region,
            }
            payload = self._get(endpoint="/search/movie", params=params)
            results = list(payload.get("results") or [])
            filtered_results = self._filter_search_results(
                results=results,
                genre_ids=genre_filter,
                date_from=date_from,
                date_to=date_to,
                year_from=year_from,
                year_to=year_to,
                category=category_value,
            )
            return {
                "page": payload.get("page", page),
                "total_pages": payload.get("total_pages", 1),
                "total_results": payload.get("total_results", len(filtered_results)),
                "results": filtered_results,
            }

        return self._discover_candidates(
            category=category_value,
            page=page,
            genre_ids=genre_filter,
            date_from=date_from,
            date_to=date_to,
            year_from=year_from,
            year_to=year_to,
        )

    def _fetch_upcoming(self, page: int) -> list[dict]:
        today = date.today()
        payload = self._get(
            endpoint="/discover/movie",
            params={
                "include_adult": "false",
                "include_video": "false",
                "language": HOLLYWOOD_LANGUAGE,
                "page": page,
                "region": settings.tmdb_region,
                "sort_by": "popularity.desc",
                "with_original_language": HOLLYWOOD_ORIGINAL_LANGUAGE,
                "with_genres": "|".join(str(genre_id) for genre_id in ALLOWED_GENRE_IDS),
                "primary_release_date.gte": settings.tmdb_upcoming_start_date or (today + timedelta(days=1)).isoformat(),
                "primary_release_date.lte": settings.tmdb_upcoming_end_date or (today + timedelta(days=365)).isoformat(),
            },
        )
        return payload.get("results", [])

    def _fetch_discover(self, category: str, page: int) -> list[dict]:
        today = date.today()
        params = {
            "include_adult": "false",
            "include_video": "false",
            "language": HOLLYWOOD_LANGUAGE,
            "page": page,
            "region": settings.tmdb_region,
            "sort_by": "popularity.desc",
            "with_original_language": HOLLYWOOD_ORIGINAL_LANGUAGE,
            "with_genres": "|".join(str(genre_id) for genre_id in ALLOWED_GENRE_IDS),
        }

        if category == "released":
            params["primary_release_date.gte"] = settings.tmdb_released_start_date or (today - timedelta(days=365 * 5)).isoformat()
            params["primary_release_date.lte"] = settings.tmdb_released_end_date or today.isoformat()

        payload = self._get(
            endpoint="/discover/movie",
            params=params,
        )
        return payload.get("results", [])

    def _discover_candidates(
        self,
        *,
        category: str,
        page: int,
        genre_ids: list[int],
        date_from: str | None,
        date_to: str | None,
        year_from: int | None,
        year_to: int | None,
    ) -> dict:
        today = date.today()
        params = {
            "include_adult": "false",
            "include_video": "false",
            "language": HOLLYWOOD_LANGUAGE,
            "page": page,
            "region": settings.tmdb_region,
            "sort_by": "popularity.desc",
            "with_original_language": HOLLYWOOD_ORIGINAL_LANGUAGE,
            "with_genres": "|".join(str(genre_id) for genre_id in genre_ids),
        }

        normalized_date_from = self._normalize_date(date_from)
        normalized_date_to = self._normalize_date(date_to)

        if normalized_date_from:
            params["primary_release_date.gte"] = normalized_date_from
        elif year_from:
            params["primary_release_date.gte"] = f"{year_from}-01-01"
        if normalized_date_to:
            params["primary_release_date.lte"] = normalized_date_to
        elif year_to:
            params["primary_release_date.lte"] = f"{year_to}-12-31"

        if category == "upcoming":
            params["primary_release_date.gte"] = params.get(
                "primary_release_date.gte",
                settings.tmdb_upcoming_start_date or (today + timedelta(days=1)).isoformat(),
            )
            params["primary_release_date.lte"] = params.get(
                "primary_release_date.lte",
                settings.tmdb_upcoming_end_date or (today + timedelta(days=365)).isoformat(),
            )

        if category == "released":
            params["primary_release_date.gte"] = params.get(
                "primary_release_date.gte",
                settings.tmdb_released_start_date or (today - timedelta(days=365 * 5)).isoformat(),
            )
            params["primary_release_date.lte"] = params.get(
                "primary_release_date.lte",
                settings.tmdb_released_end_date or today.isoformat(),
            )

        endpoint = "/trending/movie/week" if category == "trending" else "/discover/movie"
        payload = self._get(endpoint=endpoint, params=params if endpoint != "/trending/movie/week" else {"language": HOLLYWOOD_LANGUAGE, "page": page})
        results = list(payload.get("results") or [])
        if endpoint == "/trending/movie/week":
            results = self._filter_search_results(
                results=results,
                genre_ids=genre_ids,
                date_from=normalized_date_from,
                date_to=normalized_date_to,
                year_from=year_from,
                year_to=year_to,
                category=category,
            )
        return {
            "page": payload.get("page", page),
            "total_pages": payload.get("total_pages", 1),
            "total_results": payload.get("total_results", len(results)),
            "results": results,
        }

    def _filter_search_results(
        self,
        *,
        results: list[dict],
        genre_ids: list[int],
        date_from: str | None,
        date_to: str | None,
        year_from: int | None,
        year_to: int | None,
        category: str,
    ) -> list[dict]:
        filtered: list[dict] = []
        today = date.today()
        for movie in results:
            movie_genres = set(movie.get("genre_ids") or [])
            if genre_ids and not movie_genres.intersection(genre_ids):
                continue
            if movie.get("original_language") and movie.get("original_language") != HOLLYWOOD_ORIGINAL_LANGUAGE:
                continue

            release_date = str(movie.get("release_date") or "")
            release_year = None
            if len(release_date) >= 4 and release_date[:4].isdigit():
                release_year = int(release_date[:4])

            if date_from and release_date and release_date < date_from:
                continue
            if date_to and release_date and release_date > date_to:
                continue
            if year_from and release_year and release_year < year_from:
                continue
            if year_to and release_year and release_year > year_to:
                continue

            if category == "upcoming" and release_date and release_date < today.isoformat():
                continue
            if category == "released" and release_date and release_date > today.isoformat():
                continue

            filtered.append(movie)
        return filtered

    @staticmethod
    def _normalize_date(raw_value: str | None) -> str | None:
        if not raw_value:
            return None
        value = raw_value.strip()
        if len(value) != 10:
            return None
        try:
            year, month, day = value.split("-")
            if len(year) == 4 and len(month) == 2 and len(day) == 2:
                date.fromisoformat(value)
                return value
        except ValueError:
            return None
        return None

    def _fetch_trending(self, page: int) -> list[dict]:
        payload = self._get(
            endpoint="/trending/movie/week",
            params={"language": HOLLYWOOD_LANGUAGE, "page": page},
        )
        return payload.get("results", [])

    def _discover_general(
        self,
        *,
        page: int,
        language: str,
        include_adult: bool,
        genre_id: int | None,
        original_language: str | None,
        region: str | None,
        date_from: str | None,
        date_to: str | None,
        vote_average_min: float | None,
        vote_count_min: int | None,
        sort_by: str,
    ) -> dict:
        params = {
            "include_adult": str(include_adult).lower(),
            "include_video": "false",
            "language": language,
            "page": page,
            "sort_by": sort_by,
        }
        if genre_id is not None:
            params["with_genres"] = str(genre_id)
        if original_language:
            params["with_original_language"] = original_language
        if region:
            params["region"] = region
        if date_from:
            params["primary_release_date.gte"] = date_from
        if date_to:
            params["primary_release_date.lte"] = date_to
        if vote_average_min is not None:
            params["vote_average.gte"] = vote_average_min
        if vote_count_min is not None:
            params["vote_count.gte"] = vote_count_min
        payload = self._get(endpoint="/discover/movie", params=params)
        return {
            "page": int(payload.get("page") or page),
            "total_pages": int(payload.get("total_pages") or 1),
            "total_results": int(payload.get("total_results") or 0),
            "results": list(payload.get("results") or []),
        }

    def _filter_general_results(
        self,
        *,
        results: list[dict],
        genre_id: int | None,
        original_language: str | None,
        date_from: str | None,
        date_to: str | None,
        include_adult: bool,
        vote_average_min: float | None,
        vote_count_min: int | None,
    ) -> list[dict]:
        filtered: list[dict] = []
        for movie in results:
            if not include_adult and movie.get("adult"):
                continue
            movie_genre_ids = set(movie.get("genre_ids") or [])
            if genre_id is not None and genre_id not in movie_genre_ids:
                continue
            if original_language and str(movie.get("original_language") or "") != original_language:
                continue
            release_date = str(movie.get("release_date") or "")
            if date_from and release_date and release_date < date_from:
                continue
            if date_to and release_date and release_date > date_to:
                continue
            vote_average = movie.get("vote_average")
            vote_count = movie.get("vote_count")
            if vote_average_min is not None and vote_average is not None and float(vote_average) < vote_average_min:
                continue
            if vote_count_min is not None and vote_count is not None and int(vote_count) < vote_count_min:
                continue
            filtered.append(movie)
        return filtered

    def _sort_results_locally(self, *, results: list[dict], sort_by: str) -> list[dict]:
        field, direction = sort_by.split(".")
        reverse = direction == "desc"
        field_map = {
            "popularity": "popularity",
            "primary_release_date": "release_date",
            "vote_average": "vote_average",
            "vote_count": "vote_count",
            "revenue": "revenue",
            "original_title": "original_title",
        }
        result_field = field_map[field]

        def sort_key(movie: dict):
            value = movie.get(result_field)
            if result_field in {"popularity", "vote_average", "vote_count", "revenue"}:
                return float(value or 0)
            return str(value or "")

        return sorted(results, key=sort_key, reverse=reverse)

    def _get_cached_config(self, cache_key: str):
        cached = self._config_cache.get(cache_key)
        if not cached:
            return None
        expires_at, value = cached
        if expires_at < datetime.now(timezone.utc).timestamp():
            self._config_cache.pop(cache_key, None)
            return None
        return value

    def _set_cached_config(self, cache_key: str, value: object) -> None:
        self._config_cache[cache_key] = (
            (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp(),
            value,
        )

    @staticmethod
    def resolve_date_range(
        *,
        year: int | None,
        month: int | None,
        date_from: str | None,
        date_to: str | None,
    ) -> tuple[str | None, str | None]:
        normalized_date_from = TMDBService._normalize_date(date_from)
        normalized_date_to = TMDBService._normalize_date(date_to)
        current_year = date.today().year
        if year is not None and (year < 1880 or year > current_year + 10):
            raise LookupError(f"year must be between 1880 and {current_year + 10}")
        if month is not None and year is None:
            raise LookupError("year is required when month is provided")
        if month is not None and (month < 1 or month > 12):
            raise LookupError("month must be between 1 and 12")
        if normalized_date_from or normalized_date_to:
            if normalized_date_from and normalized_date_to and normalized_date_from > normalized_date_to:
                raise LookupError("date_from cannot be after date_to")
            return normalized_date_from, normalized_date_to
        if year is not None and month is not None:
            last_day = monthrange(year, month)[1]
            return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"
        if year is not None:
            return f"{year:04d}-01-01", f"{year:04d}-12-31"
        return None, None

    @staticmethod
    def build_selector_movie_payload(movie: dict, genre_map: dict[int, str], selected_ids: set[int]) -> dict:
        genre_ids = [int(item) for item in (movie.get("genre_ids") or []) if isinstance(item, int)]
        release_date = movie.get("release_date")
        release_year = None
        if isinstance(release_date, str) and len(release_date) >= 4 and release_date[:4].isdigit():
            release_year = int(release_date[:4])
        poster_path = movie.get("poster_path")
        backdrop_path = movie.get("backdrop_path")
        tmdb_id = int(movie["id"])
        return {
            "tmdb_id": tmdb_id,
            "title": movie.get("title") or movie.get("original_title"),
            "original_title": movie.get("original_title"),
            "overview": movie.get("overview"),
            "release_date": release_date,
            "release_year": release_year,
            "original_language": movie.get("original_language"),
            "genre_ids": genre_ids,
            "genre_names": [genre_map[item] for item in genre_ids if item in genre_map],
            "poster_path": poster_path,
            "poster_url": f"{TMDB_IMAGE_BASE_URL}{poster_path}" if poster_path else None,
            "backdrop_path": backdrop_path,
            "backdrop_url": f"{TMDB_IMAGE_BASE_URL}{backdrop_path}" if backdrop_path else None,
            "vote_average": movie.get("vote_average"),
            "vote_count": movie.get("vote_count"),
            "popularity": movie.get("popularity"),
            "adult": bool(movie.get("adult")),
            "video": bool(movie.get("video")),
            "is_selected": tmdb_id in selected_ids,
        }

    def _get(self, endpoint: str, params: dict) -> dict:
        request_params = dict(params)
        if settings.tmdb_api_key:
            request_params["api_key"] = settings.tmdb_api_key
        connection_attempts = max(1, int(settings.tmdb_retry_count) + 1)
        for attempt in range(connection_attempts):
            try:
                response = self.session.get(
                    f"{self.base_url}{endpoint}",
                    headers=self.headers,
                    params=request_params,
                    timeout=self.timeout,
                    verify=self.verify,
                )
                response.raise_for_status()
                return response.json()
            except SSLError as exc:
                raise ValueError(
                    "TMDB SSL verification failed. Set TMDB_CA_BUNDLE to your corporate CA bundle path, "
                    "or for local testing only set TMDB_SSL_VERIFY=false in .env and restart the server."
                ) from exc
            except Timeout as exc:
                raise ValueError(
                    "TMDB request timed out. Increase TMDB_TIMEOUT_SECONDS or check whether your network blocks TMDB."
                ) from exc
            except ConnectionError as exc:
                self.session.close()
                if attempt >= connection_attempts - 1:
                    raise ValueError(
                        "TMDB connection failed after fresh DNS/session retries. If you are behind a proxy/firewall, "
                        "set TMDB_USE_ENV_PROXY=true and configure HTTPS_PROXY/HTTP_PROXY, or set "
                        "TMDB_USE_ENV_PROXY=false to bypass broken proxy settings."
                    ) from exc
                self.session = self._build_session()
                time.sleep(min(0.25 * (2**attempt), 1.0))
            except RequestException as exc:
                raise ValueError(f"TMDB request failed: {exc}") from exc

        raise ValueError("TMDB connection failed after retries.")
