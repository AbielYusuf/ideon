"""Business logic for Website Tracker."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from database import DEFAULT_WEBSITE_DOMAIN, initialize_database
from website_tracker_models import ActivityCreate, ActivityUpdate
from website_tracker_sitemap import (
    SitemapError,
    parse_sitemap,
)
from website_tracker_store import (
    create_activity,
    delete_activity,
    get_activity,
    get_url,
    get_website,
    get_website_by_domain,
    import_urls,
    list_activities,
    list_activities_for_url,
    list_urls,
    list_websites,
    update_activity,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class WebsiteTrackerError(ValueError):
    """Base class for expected Website Tracker failures."""


class UrlNotFoundError(WebsiteTrackerError):
    pass


class ActivityNotFoundError(WebsiteTrackerError):
    pass


class WebsiteNotFoundError(WebsiteTrackerError):
    pass


class WebsiteMismatchError(WebsiteTrackerError):
    pass


class InvalidImportError(WebsiteTrackerError):
    pass


def _domain_matches(hostname: str | None, domain: str) -> bool:
    if not hostname:
        return False
    host = hostname.lower().rstrip(".")
    canonical = domain.lower().rstrip(".")
    if canonical.startswith("www."):
        canonical = canonical[4:]
    return host == canonical or host == f"www.{canonical}"


class WebsiteTrackerService:
    def __init__(self) -> None:
        initialize_database()

    # ------------------------------------------------------------------
    # Websites
    # ------------------------------------------------------------------

    def list_websites(self) -> list[dict]:
        return list_websites()

    def get_website_detail(self, website_id: int) -> dict:
        row = get_website(website_id)
        if row is None:
            raise WebsiteNotFoundError("Website not found.")
        return row

    def _require_website(self, website_id: int) -> dict:
        row = get_website(website_id)
        if row is None:
            raise WebsiteNotFoundError("Website not found.")
        return row

    def _default_website(self) -> dict:
        row = get_website_by_domain(DEFAULT_WEBSITE_DOMAIN)
        if row is None:
            raise WebsiteNotFoundError("The default website is not registered.")
        return row

    # ------------------------------------------------------------------
    # URL Library
    # ------------------------------------------------------------------

    def list_urls(
        self,
        *,
        website_id: int | None = None,
        search: str | None = None,
        status: str | None = None,
        sort: str = "url",
        order: str = "asc",
    ) -> list[dict]:
        if website_id is not None:
            self._require_website(website_id)
        return list_urls(
            website_id=website_id,
            search=search,
            status=status,
            sort=sort,
            order=order,
        )

    def get_url_detail(self, url_id: int, website_id: int | None = None) -> dict:
        row = get_url(url_id, website_id)
        if row is None:
            raise UrlNotFoundError("Website URL not found.")
        result = dict(row)
        result["activities"] = list_activities_for_url(url_id)
        return result

    def list_url_activities(self, url_id: int) -> list[dict]:
        if get_url(url_id) is None:
            raise UrlNotFoundError("Website URL not found.")
        return list_activities_for_url(url_id)

    # ------------------------------------------------------------------
    # Activities
    # ------------------------------------------------------------------

    def list_activities(
        self,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        status: str | None = None,
        activity_type: str | None = None,
        website_id: int | None = None,
        website_url_id: int | None = None,
    ) -> list[dict]:
        if website_id is not None:
            self._require_website(website_id)
        return list_activities(
            start_date=start_date,
            end_date=end_date,
            status=status,
            activity_type=activity_type,
            website_id=website_id,
            website_url_id=website_url_id,
        )

    def get_activity(self, activity_id: int) -> dict:
        row = get_activity(activity_id)
        if row is None:
            raise ActivityNotFoundError("Activity not found.")
        return row

    def _resolve_activity_website(
        self,
        website_id: int | None,
        website_url_id: int | None,
    ) -> int:
        """Validate a website/URL pair and return the authoritative website id."""
        if website_url_id is not None:
            url_row = get_url(website_url_id)
            if url_row is None:
                raise UrlNotFoundError("Associated website URL not found.")
            if website_id is not None and website_id != url_row["website_id"]:
                raise WebsiteMismatchError(
                    "The selected URL belongs to a different website."
                )
            return int(url_row["website_id"])

        if website_id is not None:
            self._require_website(website_id)
            return website_id

        return int(self._default_website()["id"])

    def create_activity(self, payload: ActivityCreate) -> dict:
        website_id = self._resolve_activity_website(
            payload.website_id, payload.website_url_id
        )

        completed_date = payload.completed_date
        if payload.status == "completed" and completed_date is None:
            completed_date = date.today()

        return create_activity(
            title=payload.title,
            description=payload.description,
            activity_type=payload.activity_type,
            status=payload.status,
            website_id=website_id,
            website_url_id=payload.website_url_id,
            planned_date=payload.planned_date.isoformat(),
            completed_date=completed_date.isoformat() if completed_date else None,
        )

    def update_activity(self, activity_id: int, payload: ActivityUpdate) -> dict:
        current = get_activity(activity_id)
        if current is None:
            raise ActivityNotFoundError("Activity not found.")

        changes: dict = {}
        for field in (
            "title",
            "description",
            "activity_type",
            "status",
            "website_id",
            "website_url_id",
            "planned_date",
            "completed_date",
        ):
            value = getattr(payload, field)
            if field in {"website_id", "website_url_id"}:
                # ``None`` is meaningful for the URL link: it removes it.
                if field in payload.model_fields_set:
                    changes[field] = value
                continue
            if value is not None:
                changes[field] = (
                    value.isoformat() if isinstance(value, date) else value
                )

        candidate_url_id = changes.get(
            "website_url_id",
            current["website_url_id"]
            if "website_url_id" not in changes
            else changes["website_url_id"],
        )
        candidate_website_id = changes.get("website_id", current["website_id"])
        resolved_website_id = self._resolve_activity_website(
            candidate_website_id,
            candidate_url_id,
        )
        changes["website_id"] = resolved_website_id

        resulting_status = changes.get("status", current["status"])
        if resulting_status == "planned":
            if changes.get("completed_date") is not None:
                raise WebsiteTrackerError(
                    "completed_date is only allowed for completed activities."
                )
            changes["completed_date"] = None
        elif "status" in changes and "completed_date" not in changes:
            # Transitioning to completed without an explicit date defaults to today.
            changes["completed_date"] = date.today().isoformat()
        elif (
            "completed_date" in changes
            and changes["completed_date"] is None
            and current["completed_date"] is None
        ):
            changes["completed_date"] = date.today().isoformat()

        return update_activity(activity_id, changes)  # type: ignore[return-value]

    def complete_activity(self, activity_id: int, completed_date: date | None) -> dict:
        current = get_activity(activity_id)
        if current is None:
            raise ActivityNotFoundError("Activity not found.")
        return update_activity(
            activity_id,
            {
                "status": "completed",
                "completed_date": (completed_date or date.today()).isoformat(),
            },
        )  # type: ignore[return-value]

    def delete_activity(self, activity_id: int) -> None:
        if not delete_activity(activity_id):
            raise ActivityNotFoundError("Activity not found.")

    # ------------------------------------------------------------------
    # Sitemap import
    # ------------------------------------------------------------------

    def list_sitemap_files(self) -> list[dict]:
        if not PROJECT_ROOT.is_dir():
            return []
        files = sorted(
            path.name
            for path in PROJECT_ROOT.iterdir()
            if path.is_file() and path.suffix.lower() == ".xml"
        )
        return [{"filename": filename} for filename in files]

    def _resolve_sitemap_file(self, filename: str) -> Path:
        cleaned = filename.strip()
        if not cleaned:
            raise InvalidImportError("A sitemap filename is required.")
        if Path(cleaned).name != cleaned:
            raise InvalidImportError(
                "Sitemap filenames must not contain directory components."
            )
        if Path(cleaned).suffix.lower() != ".xml":
            raise InvalidImportError("Only .xml sitemap files can be imported.")

        try:
            candidate = (PROJECT_ROOT / cleaned).resolve()
        except OSError as error:
            raise InvalidImportError("The sitemap file could not be resolved.") from error

        if candidate.parent != PROJECT_ROOT.resolve() or not candidate.is_file():
            raise InvalidImportError("The sitemap file was not found in the project root.")
        return candidate

    def _local_child_path(self, location: str) -> Path | None:
        """Resolve a sitemap-index child only when it is a local project file."""
        try:
            name = Path(urlsplit(location).path).name
        except ValueError:
            return None
        if not name or Path(name).suffix.lower() != ".xml":
            return None

        try:
            candidate = (PROJECT_ROOT / name).resolve()
        except OSError:
            return None
        if candidate.parent != PROJECT_ROOT.resolve() or not candidate.is_file():
            return None
        return candidate

    def import_sitemaps(
        self, filenames: list[str], website_id: int | None = None
    ) -> dict:
        if not filenames:
            raise InvalidImportError("Select at least one sitemap file to import.")

        website = (
            self._require_website(website_id)
            if website_id is not None
            else self._default_website()
        )
        website_id = int(website["id"])
        domain = str(website["domain"])

        parsed_files = 0
        found = 0
        invalid = 0
        sitemap_index = False
        child_sitemaps_skipped = 0
        unrelated_domains = 0
        records: list[tuple[str, str | None]] = []

        visited: set[Path] = set()
        pending = [self._resolve_sitemap_file(name) for name in filenames]

        while pending:
            path = pending.pop(0)
            if path in visited:
                continue
            visited.add(path)

            try:
                result = parse_sitemap(path)
            except SitemapError as error:
                raise InvalidImportError(str(error)) from error

            parsed_files += 1
            if result.is_index:
                sitemap_index = True
                for location in result.child_locations:
                    child = self._local_child_path(location)
                    if child is None or child in visited:
                        child_sitemaps_skipped += 1
                        continue
                    pending.append(child)
                continue

            found += len(result.urls) + result.skipped
            invalid += result.skipped
            for url, last_modified in result.urls:
                hostname = urlsplit(url).hostname
                if _domain_matches(hostname, domain):
                    records.append((url, last_modified))
                else:
                    unrelated_domains += 1

        imported, duplicates, updated = import_urls(website_id, records)

        return {
            "website_id": website_id,
            "website_name": website["name"],
            "filenames": list(filenames),
            "files_processed": parsed_files,
            "found": found,
            "imported": imported,
            "updated": updated,
            "skipped": invalid,
            "duplicates": duplicates,
            "invalid": invalid,
            "unrelated_domains": unrelated_domains,
            "sitemap_index": sitemap_index,
            "child_sitemaps_skipped": child_sitemaps_skipped,
        }
