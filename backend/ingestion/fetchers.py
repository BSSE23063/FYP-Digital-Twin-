"""
Profile import from external platforms — currently GitHub only.

LinkedIn is deliberately NOT implemented here: its Terms of Service prohibit
scraping, it actively blocks automated access, and its official API doesn't
expose arbitrary public-profile data to third-party apps without a business
partnership. The user's explicit call (session 15): skip it for now rather
than build something ToS-violating or pay for a third-party scraper — a
LinkedIn profile can still be added today via the existing "Add a text note"
box (copy/paste), no new code needed for that path.

GitHub has none of those problems — a public, documented, unauthenticated-
capable REST API — so it's the one actually built.
"""
import requests

from backend.config import settings

GITHUB_API = "https://api.github.com"
# Keep the request count fixed and small (2 calls total) rather than also
# fetching each repo's README — unauthenticated GitHub API calls are capped
# at 60/hour per IP (see Settings.GITHUB_TOKEN), and a README-per-repo fetch
# would multiply that fast for anyone with more than a couple dozen repos.
# Profile + repo list is already enough text for grounding; richer per-repo
# content is a reasonable future enhancement, not required for this to work.
MAX_REPOS = 30


class FetchError(Exception):
    """Raised with a message safe to show the user directly (not a raw
    exception string) — the API layer re-raises these as 422s."""


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "t2-rag"}
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"
    return headers


def fetch_github_profile(username: str) -> str:
    """Fetches a public GitHub profile + repo list and formats it as plain
    text, ready to go straight into IngestionPipeline.ingest_text() exactly
    like a typed note — same chunking/embedding path, no special casing
    downstream of this function."""
    username = username.strip().lstrip("@")
    if not username:
        raise FetchError("GitHub username can't be empty")

    try:
        profile_resp = requests.get(f"{GITHUB_API}/users/{username}", headers=_headers(), timeout=10)
    except requests.RequestException as e:
        raise FetchError(f"Couldn't reach GitHub: {e}") from e

    if profile_resp.status_code == 404:
        raise FetchError(f'No GitHub user found for "{username}"')
    if profile_resp.status_code == 403:
        raise FetchError(
            "GitHub API rate limit hit. This happens fast without a token — "
            "set GITHUB_TOKEN in .env to raise the limit from 60 to 5000 requests/hour."
        )
    profile_resp.raise_for_status()
    profile = profile_resp.json()

    try:
        repos_resp = requests.get(
            f"{GITHUB_API}/users/{username}/repos",
            headers=_headers(),
            params={"sort": "updated", "per_page": MAX_REPOS},
            timeout=10,
        )
        repos_resp.raise_for_status()
        repos = repos_resp.json()
    except requests.RequestException:
        repos = []  # profile alone is still useful; don't fail the whole import over this

    lines = [f"GitHub profile: {profile.get('name') or username} (@{username})"]
    if profile.get("bio"):
        lines.append(f"Bio: {profile['bio']}")
    if profile.get("company"):
        lines.append(f"Company: {profile['company']}")
    if profile.get("location"):
        lines.append(f"Location: {profile['location']}")
    if profile.get("blog"):
        lines.append(f"Website: {profile['blog']}")
    lines.append(
        f"{profile.get('public_repos', 0)} public repositories, "
        f"{profile.get('followers', 0)} followers"
    )

    non_forks = [r for r in repos if not r.get("fork")]
    if non_forks:
        lines.append("\nRepositories:")
        for r in non_forks:
            desc = f" — {r['description']}" if r.get("description") else ""
            lang = f" [{r['language']}]" if r.get("language") else ""
            stars = r.get("stargazers_count", 0)
            star_note = f", {stars}★" if stars else ""
            lines.append(f"- {r['name']}{lang}{desc}{star_note}")

    return "\n".join(lines)
