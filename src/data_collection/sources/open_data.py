"""Composite data source that stitches information from open and paid APIs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from ..config import RuntimeConfig
from ..http import CachedAsyncClient, gather_with_concurrency
from .base import DataSource

POSITIVE_WORDS = {
    "growth",
    "record",
    "expansion",
    "partnership",
    "award",
    "funding",
    "increase",
    "positive",
    "leader",
}
NEGATIVE_WORDS = {
    "scam",
    "fraud",
    "lawsuit",
    "decline",
    "layoff",
    "negative",
    "loss",
    "risk",
    "slowdown",
}


class OpenDataSource(DataSource):
    """Collect signals by combining multiple reliable information sources."""

    name = "open_data"

    def __init__(self, *, config: RuntimeConfig) -> None:
        self.config = config
        self.client = CachedAsyncClient(
            cache_dir=config.cache_dir, timeout=config.request_timeout
        )
        self.serp_key = config.api_keys.serpapi_key
        self.news_key = config.api_keys.newsapi_key
        self.crunchbase_key = config.api_keys.crunchbase_key
        self.producthunt_token = config.api_keys.producthunt_token
        self.proxycurl_key = config.api_keys.proxycurl_key
        self.opencorporates_token = config.api_keys.opencorporates_token

    async def fetch(self, query: Dict[str, Any]) -> Dict[str, Any]:
        startup_name = query.get("name")
        if not startup_name and not query.get("domain"):
            raise ValueError("`name` or `domain` must be provided to fetch startup data")

        domain = query.get("domain")
        local_profile = query.get("profile_path")

        payload: Dict[str, Any] = {}
        if local_profile:
            payload = self._load_local_profile(Path(local_profile))

        tasks: List[Any] = [
            self._serp_company_overview(startup_name, domain),
            self._serp_job_postings(startup_name),
            self._news_sentiment(startup_name or domain),
            self._crunchbase_profile(startup_name),
            self._producthunt_signals(startup_name),
            self._opencorporates_filings(startup_name),
        ]
        results = await gather_with_concurrency(self.config.max_concurrency, *tasks)
        for result in results:
            payload = self._deep_merge(payload, result)

        resolved_domain = payload.get("profile", {}).get("domain") or domain
        if resolved_domain:
            payload.setdefault("profile", {})["domain"] = resolved_domain

        founders = payload.get("founders", [])
        if founders:
            enriched = await self._proxycurl_enrich_founders(founders, resolved_domain)
            if enriched:
                payload["founders"] = enriched

        payload.setdefault("profile", {})["name"] = (
            payload.get("profile", {}).get("name") or startup_name
        )
        return payload

    # ------------------------------------------------------------------
    def _load_local_profile(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path)
        import json

        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _deep_merge(self, base: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in update.items():
            if key not in base:
                base[key] = value
                continue
            if isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = self._deep_merge(base[key], value)
            elif isinstance(base[key], list) and isinstance(value, list):
                base[key].extend(value)
            elif value is not None:
                base[key] = value
        return base

    async def _serp_company_overview(
        self, name: Optional[str], domain: Optional[str]
    ) -> Dict[str, Any]:
        if not name or not self.serp_key:
            profile: Dict[str, Any] = {}
            if name:
                profile["name"] = name
            if domain:
                profile["domain"] = domain
            return {"profile": profile} if profile else {}

        params = {
            "engine": "google",
            "q": name,
            "num": 5,
            "api_key": self.serp_key,
        }
        try:
            data = await self.client.get_json(
                "https://serpapi.com/search.json", params=params
            )
        except Exception:
            return {"profile": {"name": name, "domain": domain}}

        profile: Dict[str, Any] = {"name": name}
        knowledge = data.get("knowledge_graph", {})
        if knowledge:
            profile["description"] = knowledge.get("description") or knowledge.get("title")
            if knowledge.get("website"):
                profile["domain"] = self._extract_domain(knowledge["website"])
            if knowledge.get("founding_date"):
                profile["founded_year"] = self._parse_year(knowledge.get("founding_date"))
            if knowledge.get("headquarters_location"):
                profile["headquarters"] = knowledge.get("headquarters_location")
            industries = knowledge.get("categories") or []
            if isinstance(industries, list) and industries:
                profile["categories"] = industries
                profile["market_size"] = self._market_bucket_from_categories(industries)

        organic = data.get("organic_results", [])
        if organic:
            top = organic[0]
            snippet = top.get("snippet")
            if snippet and "description" not in profile:
                profile["description"] = snippet
            link = top.get("link")
            if link and "domain" not in profile:
                profile["domain"] = self._extract_domain(link)

        if domain and "domain" not in profile:
            profile["domain"] = domain
        return {"profile": profile}

    async def _serp_job_postings(self, name: Optional[str]) -> Dict[str, Any]:
        if not name or not self.serp_key:
            return {}
        params = {
            "engine": "google",
            "q": f"\"{name}\" jobs",
            "num": 10,
            "api_key": self.serp_key,
        }
        try:
            data = await self.client.get_json(
                "https://serpapi.com/search.json", params=params
            )
        except Exception:
            return {}

        search_info = data.get("search_information", {})
        total_results = float(search_info.get("total_results", 0) or 0)
        organic = data.get("organic_results", [])
        job_hits = [
            item
            for item in organic
            if "job" in (item.get("title", "") + item.get("snippet", "")).lower()
        ]
        net_new_roles = min(len(job_hits) * 3, 40)
        senior_mentions = sum(
            1
            for item in job_hits
            if any(word in (item.get("title", "") + item.get("snippet", "")).lower()
                   for word in ("senior", "lead", "principal"))
        )
        senior_ratio = senior_mentions / len(job_hits) if job_hits else 0.0
        return {
            "hiring": {
                "job_postings": int(total_results),
                "net_new_roles_last_quarter": net_new_roles,
                "senior_ratio": round(senior_ratio, 2),
            }
        }

    async def _news_sentiment(self, keyword: Optional[str]) -> Dict[str, Any]:
        if not keyword or not self.news_key:
            return {"sentiment": {"overall": "Unknown", "average": 0.0, "article_count": 0}}
        params = {
            "q": keyword,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 20,
            "apiKey": self.news_key,
        }
        try:
            data = await self.client.get_json(
                "https://newsapi.org/v2/everything", params=params
            )
        except Exception:
            return {"sentiment": {"overall": "Unknown", "average": 0.0, "article_count": 0}}

        articles = data.get("articles", [])
        scores: List[float] = []
        sources: List[str] = []
        for article in articles:
            text = " ".join(
                part
                for part in [article.get("title"), article.get("description"), article.get("content")]
                if part
            )
            if not text:
                continue
            scores.append(self._sentiment_score(text))
            if article.get("url"):
                sources.append(article["url"])
        average = sum(scores) / len(scores) if scores else 0.0
        label = "Positive" if average > 0.2 else "Negative" if average < -0.2 else "Neutral"
        return {
            "sentiment": {
                "overall": label,
                "average": round(average, 3),
                "article_count": len(scores),
                "sources": sources[:10],
            }
        }

    async def _crunchbase_profile(self, name: Optional[str]) -> Dict[str, Any]:
        if not name or not self.crunchbase_key:
            return {}
        payload = {
            "field_ids": [
                "name",
                "short_description",
                "description",
                "website_url",
                "founded_on",
                "location_identifiers",
                "rank_org",
                "categories",
                "last_funding_type",
                "last_funding_on",
                "valuation_at_last_funding",
                "num_funding_rounds",
                "num_employees_enum",
                "stock_exchange",
            ],
            "limit": 1,
            "query": [
                {"field_id": "name", "operator": "eq", "value": name},
            ],
        }
        headers = {
            "X-cb-user-key": self.crunchbase_key,
            "Content-Type": "application/json",
        }
        try:
            data = await self.client.post_json(
                "https://api.crunchbase.com/api/v4/searches/organizations",
                payload,
                headers=headers,
            )
        except Exception:
            return {}

        entities = data.get("entities", [])
        if not entities:
            return {}
        entity = entities[0]
        props = entity.get("properties", {})
        relationships = entity.get("relationships", {})

        profile: Dict[str, Any] = {
            "name": props.get("name", name),
            "description": props.get("short_description") or props.get("description"),
        }
        if props.get("website_url"):
            profile["domain"] = self._extract_domain(props["website_url"])
        if props.get("founded_on"):
            profile["founded_year"] = self._parse_year(props.get("founded_on"))
        if props.get("categories"):
            profile["categories"] = props.get("categories")
            profile["market_size"] = self._market_bucket_from_categories(
                props.get("categories")
            )
        if props.get("num_employees_enum"):
            profile["team_size"] = props.get("num_employees_enum")

        funding = {
            "stage": (props.get("last_funding_type") or "Unknown").replace("_", " ").title(),
            "valuation_trend": "Increased"
            if (props.get("valuation_at_last_funding") or {}).get("value_usd")
            else "Unknown",
            "investor_quality": self._investor_quality(relationships.get("investors", [])),
            "round_count": props.get("num_funding_rounds"),
            "last_funding_on": props.get("last_funding_on"),
        }

        founders = [
            self._map_crunchbase_founder(item)
            for item in relationships.get("founders", [])
            if item
        ]
        founders = [f for f in founders if f]

        market = {
            "size_usd": self._market_size_estimate(props.get("categories")),
            "cagr": self._market_cagr(props.get("categories")),
        }
        competition = {
            "competitor_count": len(relationships.get("competitors", [])),
            "investor_diversity": self._investor_diversity(
                relationships.get("investors", [])
            ),
        }
        return {
            "profile": profile,
            "funding": funding,
            "founders": founders,
            "market": market,
            "competition": competition,
        }

    async def _producthunt_signals(self, name: Optional[str]) -> Dict[str, Any]:
        if not name or not self.producthunt_token:
            return {}
        query = """
        query ProductSignal($term: String!) {
          posts(order: RANKING, first: 1, query: $term) {
            edges {
              node {
                name
                tagline
                votesCount
                commentsCount
                featuredAt
                reviewsRating
              }
            }
          }
        }
        """
        payload = {"query": query, "variables": {"term": name}}
        headers = {
            "Authorization": f"Bearer {self.producthunt_token}",
            "Content-Type": "application/json",
        }
        try:
            data = await self.client.post_json(
                "https://api.producthunt.com/v2/api/graphql",
                payload,
                headers=headers,
            )
        except Exception:
            return {}
        edges = (data.get("data", {}).get("posts", {}) or {}).get("edges", [])
        if not edges:
            return {}
        node = edges[0].get("node", {})
        votes = node.get("votesCount", 0) or 0
        comments = node.get("commentsCount", 0) or 0
        rating = node.get("reviewsRating") or 0
        product = {
            "tagline": node.get("tagline"),
            "pmf": self._pmf_from_votes(votes, rating),
            "innovation_mentions": "Often" if rating and rating >= 3.5 else "Sometimes",
            "frontier_tech_usage": "Emphasized" if votes > 200 else "Mentioned",
            "reviews": "Positive" if rating and rating >= 3.5 else "Mixed",
            "pivot_history": "Sometimes" if comments > 10 else "Rarely",
            "release_frequency_per_quarter": self._release_frequency(node.get("featuredAt")),
        }
        return {"product": product}

    async def _opencorporates_filings(self, name: Optional[str]) -> Dict[str, Any]:
        if not name:
            return {}
        params = {"q": name}
        if self.opencorporates_token:
            params["api_token"] = self.opencorporates_token
        try:
            data = await self.client.get_json(
                "https://api.opencorporates.com/v0.4/companies/search",
                params=params,
            )
        except Exception:
            return {}

        companies = data.get("results", {}).get("companies", [])
        if not companies:
            return {}
        company = companies[0].get("company", {})
        compliance = {
            "jurisdiction": company.get("jurisdiction_code"),
            "incorporation_date": company.get("incorporation_date"),
            "company_number": company.get("company_number"),
        }
        profile = {"legal_name": company.get("name")}
        return {"compliance": compliance, "profile": profile}

    async def _proxycurl_enrich_founders(
        self, founders: Iterable[Dict[str, Any]], domain: Optional[str]
    ) -> List[Dict[str, Any]]:
        if not self.proxycurl_key:
            return list(founders)

        enriched: List[Dict[str, Any]] = []
        for founder in founders:
            linkedin_url = founder.get("linkedin_url")
            name = founder.get("name")
            if not linkedin_url and name and domain:
                try:
                    search = await self.client.get_json(
                        "https://nubela.co/proxycurl/api/linkedin/company/employees/search/",
                        params={
                            "employment_role": "founder",
                            "company_domain": domain,
                            "page_size": 1,
                            "search_term": name,
                        },
                        headers=self._proxycurl_headers(),
                    )
                    candidates = search.get("employees", [])
                    if candidates:
                        linkedin_url = candidates[0].get("linkedin_profile_url")
                except Exception:
                    linkedin_url = None
            if not linkedin_url:
                enriched.append(self._default_founder_profile(founder))
                continue
            try:
                profile = await self.client.get_json(
                    "https://nubela.co/proxycurl/api/v2/linkedin",
                    params={"url": linkedin_url},
                    headers=self._proxycurl_headers(),
                )
                enriched.append(self._map_proxycurl_profile(name, profile))
            except Exception:
                enriched.append(self._default_founder_profile(founder))
        return enriched

    # ------------------------------------------------------------------
    def _extract_domain(self, url: str) -> str:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return parsed.netloc or parsed.path

    def _parse_year(self, value: Optional[str]) -> Optional[int]:
        if not value:
            return None
        try:
            return int(value[:4])
        except (TypeError, ValueError):
            return None

    def _market_bucket_from_categories(self, categories: Iterable[str]) -> str:
        if not categories:
            return "Unknown"
        normalized = {str(cat).lower() for cat in categories}
        if normalized & {"artificial intelligence", "machine learning", "ai"}:
            return "Large"
        if normalized & {"fintech", "financial services"}:
            return "Large"
        if normalized & {"security", "privacy", "compliance"}:
            return "Medium"
        return "Small"

    def _market_size_estimate(self, categories: Optional[Iterable[str]]) -> Optional[int]:
        if not categories:
            return None
        normalized = {str(cat).lower() for cat in categories}
        if normalized & {"artificial intelligence", "machine learning", "ai"}:
            return 80_000_000_000
        if normalized & {"fraud detection", "security", "compliance"}:
            return 25_000_000_000
        if normalized & {"productivity", "collaboration"}:
            return 15_000_000_000
        return 10_000_000_000

    def _market_cagr(self, categories: Optional[Iterable[str]]) -> float:
        if not categories:
            return 0.12
        normalized = {str(cat).lower() for cat in categories}
        if normalized & {"artificial intelligence", "machine learning", "ai"}:
            return 0.27
        if normalized & {"fraud detection", "security", "compliance"}:
            return 0.22
        return 0.15

    def _investor_quality(self, investors: Optional[Iterable[Dict[str, Any]]]) -> str:
        if not investors:
            return "Unknown"
        top_tier = sum(
            1
            for investor in investors
            if any(
                keyword in str(investor.get("name", "")).lower()
                for keyword in ("sequoia", "a16z", "benchmark", "accel", "yc")
            )
        )
        if top_tier:
            return "Top-tier"
        if len(list(investors)) >= 3:
            return "Recognized"
        return "Unknown"

    def _investor_diversity(self, investors: Optional[Iterable[Dict[str, Any]]]) -> float:
        if not investors:
            return 0.0
        geos = {
            investor.get("properties", {}).get("location")
            or investor.get("location_identifiers", [{}])[0].get("value")
            for investor in investors
            if investor
        }
        return round(min(len([g for g in geos if g]) / 5, 1.0), 2)

    def _map_crunchbase_founder(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        props = item.get("properties", {})
        identifier = props.get("identifier", {})
        name = identifier.get("value") or props.get("name")
        if not name:
            return None
        linkedin_url = None
        if props.get("linkedin_url"):
            linkedin_url = props.get("linkedin_url")
        elif props.get("permalink"):
            linkedin_url = f"https://www.linkedin.com/in/{props['permalink'].split('/')[-1]}"
        return {
            "name": name,
            "title": props.get("title"),
            "linkedin_url": linkedin_url,
            "education_level": "Unknown",
            "school_tier": "Unknown",
            "leadership_experience": bool(props.get("title")),
            "top_company_experience": False,
            "previous_exits": 0,
            "role_alignment": 0.0,
        }

    def _proxycurl_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.proxycurl_key}"}

    def _default_founder_profile(self, founder: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": founder.get("name", "Unknown"),
            "education_level": founder.get("education_level", "Unknown"),
            "school_tier": founder.get("school_tier", "Unknown"),
            "leadership_experience": founder.get("leadership_experience", False),
            "top_company_experience": founder.get("top_company_experience", False),
            "previous_exits": founder.get("previous_exits", 0),
            "role_alignment": founder.get("role_alignment", 0.0),
        }

    def _map_proxycurl_profile(self, fallback_name: Optional[str], profile: Dict[str, Any]) -> Dict[str, Any]:
        education_entries = profile.get("education", []) or []
        highest_education = "Unknown"
        school_tier = "Unknown"
        if education_entries:
            highest = education_entries[0]
            degree = str(highest.get("degree_name") or "").lower()
            if "phd" in degree or "doctor" in degree:
                highest_education = "PhD"
            elif "master" in degree or "msc" in degree:
                highest_education = "Masters"
            elif "bachelor" in degree or "bsc" in degree:
                highest_education = "Bachelors"
            elif degree:
                highest_education = degree.title()
            school = str(highest.get("school"))
            if school:
                school_tier = self._infer_school_tier(school)
        experience = profile.get("experience", []) or []
        leadership = any(
            exp.get("title") and any(word in exp.get("title").lower() for word in ("ceo", "cto", "founder", "head"))
            for exp in experience
        )
        top_company = any(
            any(
                keyword in str(exp.get("company", "")).lower()
                for keyword in ("google", "meta", "microsoft", "amazon", "apple", "openai", "mckinsey")
            )
            for exp in experience
        )
        exits = sum(1 for exp in experience if "acquired" in str(exp.get("description", "")).lower())
        current_roles = [exp for exp in experience if exp.get("current")]
        role_alignment = 0.0
        if current_roles:
            role_alignment = min(
                1.0,
                sum(
                    1.0
                    for exp in current_roles
                    if any(
                        keyword in str(exp.get("title", "")).lower()
                        for keyword in ("ai", "ml", "product", "research", "engineering")
                    )
                )
                / len(current_roles),
            )
        return {
            "name": profile.get("full_name") or fallback_name or "Unknown",
            "education_level": highest_education,
            "school_tier": school_tier,
            "leadership_experience": leadership,
            "top_company_experience": top_company,
            "previous_exits": exits,
            "role_alignment": role_alignment if role_alignment else 0.0,
        }

    def _infer_school_tier(self, school: str) -> str:
        name = school.lower()
        tier_1 = {"stanford", "mit", "harvard", "oxford", "cambridge", "berkeley", "princeton"}
        tier_2 = {"waterloo", "imperial", "cornell", "columbia", "ucla", "tsinghua"}
        if any(keyword in name for keyword in tier_1):
            return "Tier-1"
        if any(keyword in name for keyword in tier_2):
            return "Tier-2"
        return "Tier-3"

    def _pmf_from_votes(self, votes: int, rating: float) -> str:
        score = votes + (rating or 0) * 20
        if score > 500:
            return "Strong"
        if score > 150:
            return "Moderate"
        return "Weak"

    def _release_frequency(self, featured_at: Optional[str]) -> int:
        if not featured_at:
            return 2
        # If product was featured within last quarter, assume higher cadence
        return 6

    def _sentiment_score(self, text: str) -> float:
        text_lower = text.lower()
        positive = sum(text_lower.count(word) for word in POSITIVE_WORDS)
        negative = sum(text_lower.count(word) for word in NEGATIVE_WORDS)
        total = positive + negative
        if total == 0:
            return 0.0
        return (positive - negative) / total


__all__ = ["OpenDataSource"]
