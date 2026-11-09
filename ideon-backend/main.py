import sqlite3
from contextlib import closing
from datetime import date
from typing import NoReturn

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from assessment_models import (
    AssessmentResult,
    PrepareResponse,
    RefineRequest,
    RefinedIdea,
    ScoreRequest,
)
from assessment_service import (
    AssessmentService,
    ConfirmationRequiredError,
    IdeaNotFoundError,
)
from database import get_connection, initialize_database
from gemini_service import (
    GeminiAuthenticationError,
    GeminiConfigurationError,
    GeminiResponseError,
    GeminiService,
    GeminiTimeoutError,
    GeminiUnavailableError,
)
from improvement_models import (
    ImprovementProposalResponse,
    ImprovementSessionDetailResponse,
    ImprovementSessionResponse,
    ProposalActionRequest,
    ProposalActionResponse,
)
from improvement_service import (
    AssessmentMismatchError,
    ImprovementError,
    ImprovementService,
    InvalidProposalStateError,
    InvalidSessionStateError,
    MaximumRevisionsReachedError,
    ProposalNotFoundError,
    SessionNotFoundError,
)
from scoring import ScoringError
from auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    clear_auth_cookies,
    constant_time_equals,
    hash_token,
    set_auth_cookies,
)
from auth_models import LoginRequest, RegisterRequest, UserProfile
from auth_service import (
    AuthError,
    DuplicateEmailError,
    DuplicateUsernameError,
    InactiveAccountError,
    InvalidCredentialsError,
    public_profile,
)
import auth_service
from website_tracker_models import (
    ActivityCreate,
    ActivityUpdate,
    CompleteActivityRequest,
    SitemapFile,
    SitemapImportRequest,
    SitemapImportResponse,
    Website,
    WebsiteActivity,
    WebsiteUrl,
    WebsiteUrlDetail,
)
from website_tracker_service import (
    ActivityNotFoundError,
    InvalidImportError,
    UrlNotFoundError,
    WebsiteMismatchError,
    WebsiteNotFoundError,
    WebsiteTrackerError,
    WebsiteTrackerService,
)

app = FastAPI(title="Ideon API")

ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://ideon-opal.vercel.app",  # Domain Vercel kamu
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-CSRF-Token"],
)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def verify_csrf(request: Request) -> None:
    """Double-submit + Origin validation for authenticated mutations."""
    if request.method not in MUTATING_METHODS:
        return

    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request origin is not allowed.",
        )

    # Unauthenticated requests are rejected by get_current_user. Logout is
    # allowed to clear a broken session without a CSRF token.
    if not request.cookies.get(SESSION_COOKIE):
        return
    if request.url.path == "/api/auth/logout":
        return

    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get("x-csrf-token")
    if (
        not cookie_token
        or not header_token
        or not constant_time_equals(cookie_token, header_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed.",
        )


def get_current_user(
    request: Request,
    _: None = Depends(verify_csrf),
) -> dict:
    user = auth_service.get_session_user(request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )

    # Bind the double-submit token to this specific session.
    if (
        request.method in MUTATING_METHODS
        and request.url.path != "/api/auth/logout"
    ):
        header_token = request.headers.get("x-csrf-token")
        if (
            not header_token
            or not constant_time_equals(
                hash_token(header_token), user["csrf_hash"]
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed.",
            )

    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required.",
        )
    return user


def _raise_auth_error(error: Exception) -> NoReturn:
    if isinstance(
        error, (DuplicateEmailError, DuplicateUsernameError)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    if isinstance(error, (InvalidCredentialsError, InactiveAccountError)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
        ) from error
    if isinstance(error, AuthError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    raise error


# -------------------------------------------------------------
# Authentication Endpoints
# -------------------------------------------------------------

@app.post(
    "/api/auth/register",
    response_model=UserProfile,
    status_code=status.HTTP_201_CREATED,
)
def register_user(payload: RegisterRequest, response: Response) -> dict:
    try:
        profile, token, csrf_token = auth_service.register(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            confirm_password=payload.confirm_password,
        )
    except Exception as error:
        _raise_auth_error(error)
    set_auth_cookies(response, token, csrf_token)
    response.headers["X-CSRF-Token"] = csrf_token
    return profile


@app.post("/api/auth/login", response_model=UserProfile)
def login_user(payload: LoginRequest, response: Response) -> dict:
    try:
        profile, token, csrf_token = auth_service.login(
            payload.email, payload.password
        )
    except Exception as error:
        _raise_auth_error(error)
    set_auth_cookies(response, token, csrf_token)
    response.headers["X-CSRF-Token"] = csrf_token
    return profile


@app.post(
    "/api/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
)
def logout_user(request: Request) -> Response:
    auth_service.logout(request.cookies.get(SESSION_COOKIE))
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(response)
    return response


@app.get("/api/auth/me", response_model=UserProfile)
def current_user_profile(user: dict = Depends(get_current_user)) -> dict:
    return public_profile(user)


class IdeaCreate(BaseModel):
    title: str
    description: str

    @field_validator("title", "description")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class Idea(BaseModel):
    id: int
    title: str
    description: str
    created_at: str
    updated_at: str


class WebShortcutCreate(BaseModel):
    name: str
    url: str
    category: str = "Custom"

    @field_validator("name", "url")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("url")
    @classmethod
    def must_be_valid_http_url(cls, value: str) -> str:
        value = value.strip()
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("URL must start with http:// or https://")
        return value


class WebShortcut(BaseModel):
    id: int
    name: str
    url: str
    category: str
    created_at: str
    updated_at: str


initialize_database()

gemini_service = GeminiService()
assessment_service = AssessmentService(gemini_service)
improvement_service = ImprovementService(gemini_service)
website_tracker_service = WebsiteTrackerService()


def _raise_assessment_error(error: Exception) -> NoReturn:
    """Translate service failures into API errors."""
    if isinstance(error, (IdeaNotFoundError, SessionNotFoundError, ProposalNotFoundError)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    if isinstance(
        error,
        (
            ConfirmationRequiredError,
            InvalidSessionStateError,
            InvalidProposalStateError,
            MaximumRevisionsReachedError,
            AssessmentMismatchError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    if isinstance(error, GeminiConfigurationError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    if isinstance(error, GeminiAuthenticationError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error

    if isinstance(error, GeminiTimeoutError):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(error),
        ) from error

    if isinstance(
        error,
        (GeminiUnavailableError, GeminiResponseError, ScoringError),
    ):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error

    if isinstance(error, sqlite3.Error):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage is unavailable.",
        ) from error

    raise error


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "application": "Ideon",
        "message": "Backend is running",
    }


@app.post(
    "/api/ideas",
    response_model=Idea,
    status_code=status.HTTP_201_CREATED,
)
def create_idea(
    payload: IdeaCreate, user: dict = Depends(get_current_user)
) -> Idea:
    try:
        with closing(get_connection()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO ideas (user_id, title, description)
                    VALUES (?, ?, ?)
                    """,
                    (user["id"], payload.title, payload.description),
                )
                row = connection.execute(
                    """
                    SELECT id, title, description, created_at, updated_at
                    FROM ideas
                    WHERE id = ? AND user_id = ?
                    """,
                    (cursor.lastrowid, user["id"]),
                ).fetchone()
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the idea.",
        ) from error

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The saved idea could not be loaded.",
        )

    return Idea(**dict(row))


@app.get("/api/ideas", response_model=list[Idea])
def list_ideas(user: dict = Depends(get_current_user)) -> list[Idea]:
    try:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT id, title, description, created_at, updated_at
                FROM ideas
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (user["id"],),
            ).fetchall()
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load ideas.",
        ) from error

    return [Idea(**dict(row)) for row in rows]


@app.get("/api/ideas/{idea_id}", response_model=Idea)
def get_idea(idea_id: int, user: dict = Depends(get_current_user)) -> Idea:
    try:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT id, title, description, created_at, updated_at
                FROM ideas
                WHERE id = ? AND user_id = ?
                """,
                (idea_id, user["id"]),
            ).fetchone()
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load the idea.",
        ) from error

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Idea not found.",
        )

    return Idea(**dict(row))


@app.patch("/api/ideas/{idea_id}", response_model=Idea)
def update_idea(
    idea_id: int,
    payload: IdeaCreate,
    user: dict = Depends(get_current_user),
) -> Idea:
    try:
        with closing(get_connection()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE ideas
                    SET title = ?,
                        description = ?,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    WHERE id = ? AND user_id = ?
                    """,
                    (payload.title, payload.description, idea_id, user["id"]),
                )

                if cursor.rowcount == 0:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Idea not found.",
                    )

                row = connection.execute(
                    """
                    SELECT id, title, description, created_at, updated_at
                    FROM ideas
                    WHERE id = ? AND user_id = ?
                    """,
                    (idea_id, user["id"]),
                ).fetchone()
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update the idea.",
        ) from error

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Idea not found.",
        )

    return Idea(**dict(row))


@app.delete(
    "/api/ideas/{idea_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_idea(
    idea_id: int, user: dict = Depends(get_current_user)
) -> Response:
    try:
        with closing(get_connection()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    DELETE FROM ideas
                    WHERE id = ? AND user_id = ?
                    """,
                    (idea_id, user["id"]),
                )

                if cursor.rowcount == 0:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Idea not found.",
                    )
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete the idea.",
        ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/ideas/{idea_id}/assessment/prepare",
    response_model=PrepareResponse,
)
def prepare_assessment(
    idea_id: int, user: dict = Depends(get_current_user)
) -> PrepareResponse:
    try:
        return assessment_service.prepare(idea_id, user["id"])
    except Exception as error:
        _raise_assessment_error(error)


@app.post(
    "/api/ideas/{idea_id}/assessment/refine",
    response_model=RefinedIdea,
)
def refine_assessment(
    idea_id: int,
    payload: RefineRequest,
    user: dict = Depends(get_current_user),
) -> RefinedIdea:
    try:
        return assessment_service.refine(idea_id, payload, user["id"])
    except Exception as error:
        _raise_assessment_error(error)


@app.post(
    "/api/ideas/{idea_id}/assessment/score",
    response_model=AssessmentResult,
    status_code=status.HTTP_201_CREATED,
)
def score_assessment(
    idea_id: int,
    payload: ScoreRequest,
    user: dict = Depends(get_current_user),
) -> AssessmentResult:
    try:
        return assessment_service.score(idea_id, payload, user["id"])
    except Exception as error:
        _raise_assessment_error(error)


@app.get(
    "/api/ideas/{idea_id}/assessments",
    response_model=list[AssessmentResult],
)
def get_assessment_history(
    idea_id: int, user: dict = Depends(get_current_user)
) -> list[AssessmentResult]:
    try:
        return assessment_service.history(idea_id, user["id"])
    except Exception as error:
        _raise_assessment_error(error)


@app.post(
    "/api/ideas/{idea_id}/improvement/session",
    response_model=ImprovementSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_improvement_session(
    idea_id: int, user: dict = Depends(get_current_user)
) -> ImprovementSessionResponse:
    try:
        return improvement_service.start_session(idea_id, user["id"])
    except Exception as error:
        _raise_assessment_error(error)


@app.get(
    "/api/ideas/{idea_id}/improvement/session/active",
    response_model=ImprovementSessionDetailResponse | None,
)
def get_active_improvement_session(
    idea_id: int, user: dict = Depends(get_current_user)
) -> ImprovementSessionDetailResponse | None:
    try:
        return improvement_service.get_active_session_detail(idea_id, user["id"])
    except Exception as error:
        _raise_assessment_error(error)


@app.post(
    "/api/ideas/{idea_id}/improvement/session/{session_id}/propose",
    response_model=ImprovementProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
def propose_improvement(
    idea_id: int,
    session_id: int,
    user: dict = Depends(get_current_user),
) -> ImprovementProposalResponse:
    try:
        return improvement_service.propose(idea_id, session_id, user["id"])
    except Exception as error:
        _raise_assessment_error(error)


@app.post(
    "/api/ideas/{idea_id}/improvement/session/{session_id}/proposals/{proposal_id}/action",
    response_model=ProposalActionResponse,
)
def action_proposal(
    idea_id: int,
    session_id: int,
    proposal_id: int,
    payload: ProposalActionRequest,
    user: dict = Depends(get_current_user),
) -> ProposalActionResponse:
    try:
        return improvement_service.action_proposal(
            idea_id=idea_id,
            session_id=session_id,
            proposal_id=proposal_id,
            action=payload.action,
            user_id=user["id"],
        )
    except Exception as error:
        _raise_assessment_error(error)


@app.post(
    "/api/ideas/{idea_id}/improvement/session/{session_id}/stop",
    response_model=ImprovementSessionResponse,
)
def stop_improvement_session(
    idea_id: int,
    session_id: int,
    user: dict = Depends(get_current_user),
) -> ImprovementSessionResponse:
    try:
        return improvement_service.stop_session(idea_id, session_id, user["id"])
    except Exception as error:
        _raise_assessment_error(error)


# -------------------------------------------------------------
# Web Shortcuts Endpoints (Quick Access)
# -------------------------------------------------------------

@app.get("/api/shortcuts", response_model=list[WebShortcut])
def list_shortcuts(user: dict = Depends(get_current_user)) -> list[WebShortcut]:
    try:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT id, name, url, category, created_at, updated_at
                FROM web_shortcuts
                WHERE user_id = ?
                ORDER BY id ASC
                """,
                (user["id"],),
            ).fetchall()
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load web shortcuts.",
        ) from error

    return [WebShortcut(**dict(row)) for row in rows]


@app.post(
    "/api/shortcuts",
    response_model=WebShortcut,
    status_code=status.HTTP_201_CREATED,
)
def create_shortcut(
    payload: WebShortcutCreate, user: dict = Depends(get_current_user)
) -> WebShortcut:
    try:
        with closing(get_connection()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO web_shortcuts (user_id, name, url, category)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user["id"], payload.name, payload.url, payload.category),
                )
                row = connection.execute(
                    """
                    SELECT id, name, url, category, created_at, updated_at
                    FROM web_shortcuts
                    WHERE id = ? AND user_id = ?
                    """,
                    (cursor.lastrowid, user["id"]),
                ).fetchone()
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create shortcut.",
        ) from error

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Created shortcut could not be loaded.",
        )

    return WebShortcut(**dict(row))


@app.patch("/api/shortcuts/{shortcut_id}", response_model=WebShortcut)
def update_shortcut(
    shortcut_id: int,
    payload: WebShortcutCreate,
    user: dict = Depends(get_current_user),
) -> WebShortcut:
    try:
        with closing(get_connection()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE web_shortcuts
                    SET name = ?,
                        url = ?,
                        category = ?,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    WHERE id = ? AND user_id = ?
                    """,
                    (
                        payload.name,
                        payload.url,
                        payload.category,
                        shortcut_id,
                        user["id"],
                    ),
                )

                if cursor.rowcount == 0:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Shortcut not found.",
                    )

                row = connection.execute(
                    """
                    SELECT id, name, url, category, created_at, updated_at
                    FROM web_shortcuts
                    WHERE id = ? AND user_id = ?
                    """,
                    (shortcut_id, user["id"]),
                ).fetchone()
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update shortcut.",
        ) from error

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shortcut not found.",
        )

    return WebShortcut(**dict(row))


@app.delete(
    "/api/shortcuts/{shortcut_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_shortcut(
    shortcut_id: int, user: dict = Depends(get_current_user)
) -> Response:
    try:
        with closing(get_connection()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    DELETE FROM web_shortcuts
                    WHERE id = ? AND user_id = ?
                    """,
                    (shortcut_id, user["id"]),
                )

                if cursor.rowcount == 0:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Shortcut not found.",
                    )
    except sqlite3.Error as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete shortcut.",
        ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -------------------------------------------------------------
# Website Tracker Endpoints
# -------------------------------------------------------------

def _raise_website_tracker_error(error: Exception) -> NoReturn:
    if isinstance(
        error, (UrlNotFoundError, ActivityNotFoundError, WebsiteNotFoundError)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    if isinstance(
        error, (InvalidImportError, WebsiteMismatchError, WebsiteTrackerError)
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
    raise error


@app.get(
    "/api/website-tracker/websites",
    response_model=list[Website],
)
def list_websites(admin: dict = Depends(require_admin)) -> list[dict]:
    return website_tracker_service.list_websites()


@app.get(
    "/api/website-tracker/websites/{website_id}",
    response_model=Website,
)
def get_website(
    website_id: int, admin: dict = Depends(require_admin)
) -> dict:
    try:
        return website_tracker_service.get_website_detail(website_id)
    except Exception as error:
        _raise_website_tracker_error(error)


@app.get(
    "/api/website-tracker/urls",
    response_model=list[WebsiteUrl],
)
def list_website_urls(
    admin: dict = Depends(require_admin),
    website_id: int | None = None,
    search: str | None = None,
    status_filter: str | None = None,
    sort: str = "url",
    order: str = "asc",
) -> list[dict]:
    try:
        return website_tracker_service.list_urls(
            website_id=website_id,
            search=search,
            status=status_filter,
            sort=sort,
            order=order,
        )
    except Exception as error:
        _raise_website_tracker_error(error)


@app.get(
    "/api/website-tracker/urls/{url_id}",
    response_model=WebsiteUrlDetail,
)
def get_website_url(
    url_id: int,
    website_id: int | None = None,
    admin: dict = Depends(require_admin),
) -> dict:
    try:
        return website_tracker_service.get_url_detail(url_id, website_id)
    except Exception as error:
        _raise_website_tracker_error(error)


@app.get(
    "/api/website-tracker/urls/{url_id}/activities",
    response_model=list[WebsiteActivity],
)
def get_website_url_activities(
    url_id: int, admin: dict = Depends(require_admin)
) -> list[dict]:
    try:
        return website_tracker_service.list_url_activities(url_id)
    except Exception as error:
        _raise_website_tracker_error(error)


@app.get(
    "/api/website-tracker/sitemaps",
    response_model=list[SitemapFile],
)
def list_website_sitemaps(admin: dict = Depends(require_admin)) -> list[dict]:
    return website_tracker_service.list_sitemap_files()


@app.post(
    "/api/website-tracker/sitemaps/import",
    response_model=SitemapImportResponse,
)
def import_website_sitemaps(
    payload: SitemapImportRequest, admin: dict = Depends(require_admin)
) -> dict:
    try:
        return website_tracker_service.import_sitemaps(
            payload.filenames, payload.website_id
        )
    except Exception as error:
        _raise_website_tracker_error(error)


@app.get(
    "/api/website-tracker/activities",
    response_model=list[WebsiteActivity],
)
def list_website_activities(
    admin: dict = Depends(require_admin),
    start: date | None = None,
    end: date | None = None,
    status_filter: str | None = None,
    activity_type: str | None = None,
    website_id: int | None = None,
    website_url_id: int | None = None,
) -> list[dict]:
    try:
        return website_tracker_service.list_activities(
            start_date=start.isoformat() if start else None,
            end_date=end.isoformat() if end else None,
            status=status_filter,
            activity_type=activity_type,
            website_id=website_id,
            website_url_id=website_url_id,
        )
    except Exception as error:
        _raise_website_tracker_error(error)


@app.post(
    "/api/website-tracker/activities",
    response_model=WebsiteActivity,
    status_code=status.HTTP_201_CREATED,
)
def create_website_activity(
    payload: ActivityCreate, admin: dict = Depends(require_admin)
) -> dict:
    try:
        return website_tracker_service.create_activity(payload)
    except Exception as error:
        _raise_website_tracker_error(error)


@app.get(
    "/api/website-tracker/activities/{activity_id}",
    response_model=WebsiteActivity,
)
def get_website_activity(
    activity_id: int, admin: dict = Depends(require_admin)
) -> dict:
    try:
        return website_tracker_service.get_activity(activity_id)
    except Exception as error:
        _raise_website_tracker_error(error)


@app.patch(
    "/api/website-tracker/activities/{activity_id}",
    response_model=WebsiteActivity,
)
def update_website_activity(
    activity_id: int,
    payload: ActivityUpdate,
    admin: dict = Depends(require_admin),
) -> dict:
    try:
        return website_tracker_service.update_activity(activity_id, payload)
    except Exception as error:
        _raise_website_tracker_error(error)


@app.delete(
    "/api/website-tracker/activities/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_website_activity(
    activity_id: int, admin: dict = Depends(require_admin)
) -> Response:
    try:
        website_tracker_service.delete_activity(activity_id)
    except Exception as error:
        _raise_website_tracker_error(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/website-tracker/activities/{activity_id}/complete",
    response_model=WebsiteActivity,
)
def complete_website_activity(
    activity_id: int,
    payload: CompleteActivityRequest,
    admin: dict = Depends(require_admin),
) -> dict:
    try:
        return website_tracker_service.complete_activity(
            activity_id, payload.completed_date
        )
    except Exception as error:
        _raise_website_tracker_error(error)



