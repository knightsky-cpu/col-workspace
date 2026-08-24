import os
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable, Literal

from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token


AuthMode = Literal["local_dev", "google_oidc"]


class AuthError(Exception):
    """Base class for request authentication and ownership failures."""


class AuthRequiredError(AuthError):
    """Raised when a protected request is missing usable credentials."""


class AuthForbiddenError(AuthError):
    """Raised when credentials do not own the requested resource."""


class AuthConfigurationError(AuthError):
    """Raised when auth is enabled but required server config is missing."""


@dataclass(frozen=True)
class AuthSettings:
    mode: AuthMode = "local_dev"
    google_client_id: str | None = None


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: str | None
    subject: str | None
    email: str | None
    display_name: str | None
    workspace_project_id: str | None
    provider: AuthMode
    authenticated: bool
    local_development: bool

    def public_dict(self) -> dict[str, object]:
        return {
            "auth_contract_version": "1.0",
            "auth_mode": self.provider,
            "authenticated": self.authenticated,
            "local_development": self.local_development,
            "user_id": self.user_id,
            "workspace_project_id": self.workspace_project_id,
            "subject": self.subject,
            "email": self.email,
            "display_name": self.display_name,
        }


TokenVerifier = Callable[[str, str], Mapping[str, Any]]


def load_auth_settings(
    environ: Mapping[str, str] | None = None,
) -> AuthSettings:
    source = os.environ if environ is None else environ
    raw_mode = source.get("AGENT_COL_AUTH_MODE", "local_dev").strip().lower()
    if raw_mode not in {"local_dev", "google_oidc"}:
        raise AuthConfigurationError("Unsupported auth mode.")
    client_id = (
        source.get("GOOGLE_OAUTH_CLIENT_ID")
        or source.get("GOOGLE_CLIENT_ID")
        or None
    )
    if client_id is not None:
        client_id = client_id.strip() or None
    return AuthSettings(
        mode=raw_mode,  # type: ignore[arg-type]
        google_client_id=client_id,
    )


def default_google_token_verifier(
    token: str,
    client_id: str,
) -> Mapping[str, Any]:
    return google_id_token.verify_oauth2_token(
        token,
        google_auth_requests.Request(),
        client_id,
    )


def google_subject_to_user_id(subject: str) -> str:
    normalized = subject.strip()
    if not normalized or len(normalized) > 120:
        raise AuthForbiddenError("Google subject is invalid.")
    if not all(
        character.isalnum() or character in {"_", "-"}
        for character in normalized
    ):
        raise AuthForbiddenError("Google subject contains unsupported characters.")
    return f"google--{normalized}"


def google_subject_to_workspace_project_id(subject: str) -> str:
    normalized = subject.strip()
    if not normalized:
        raise AuthForbiddenError("Google subject is invalid.")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"project--{digest}"


def google_subject_owns_workspace_project_id(
    subject: str,
    project_id: str,
) -> bool:
    default_project_id = google_subject_to_workspace_project_id(subject)
    return (
        project_id == default_project_id
        or project_id.startswith(f"{default_project_id}--")
    )


class Authenticator:
    def __init__(
        self,
        settings: AuthSettings,
        *,
        token_verifier: TokenVerifier = default_google_token_verifier,
    ) -> None:
        self._settings = settings
        self._token_verifier = token_verifier

    @property
    def settings(self) -> AuthSettings:
        return self._settings

    def session(
        self,
        authorization_header: str | None = None,
    ) -> AuthenticatedPrincipal:
        if self._settings.mode == "local_dev":
            return AuthenticatedPrincipal(
                user_id=None,
                subject=None,
                email=None,
                display_name=None,
                workspace_project_id=None,
                provider="local_dev",
                authenticated=False,
                local_development=True,
            )
        return self.authenticate(authorization_header)

    def authenticate(
        self,
        authorization_header: str | None,
    ) -> AuthenticatedPrincipal:
        if self._settings.mode == "local_dev":
            return self.session(authorization_header)
        token = self._extract_bearer_token(authorization_header)
        client_id = self._settings.google_client_id
        if client_id is None:
            raise AuthConfigurationError(
                "Google OAuth client ID is not configured."
            )
        try:
            claims = self._token_verifier(token, client_id)
        except Exception as exc:
            raise AuthForbiddenError("Google ID token is invalid.") from exc
        subject = claims.get("sub")
        if not isinstance(subject, str):
            raise AuthForbiddenError("Google ID token is missing a stable subject.")
        return AuthenticatedPrincipal(
            user_id=google_subject_to_user_id(subject),
            subject=subject,
            email=(
                claims.get("email")
                if isinstance(claims.get("email"), str)
                else None
            ),
            display_name=(
                claims.get("name")
                if isinstance(claims.get("name"), str)
                else None
            ),
            workspace_project_id=google_subject_to_workspace_project_id(subject),
            provider="google_oidc",
            authenticated=True,
            local_development=False,
        )

    def resolve_user_id(
        self,
        *,
        supplied_user_id: str,
        authorization_header: str | None,
    ) -> str:
        if self._settings.mode == "local_dev":
            return supplied_user_id
        principal = self.authenticate(authorization_header)
        if principal.user_id != supplied_user_id:
            raise AuthForbiddenError(
                "Authenticated user does not own this request."
            )
        return supplied_user_id

    def resolve_project_id(
        self,
        *,
        supplied_project_id: str,
        authorization_header: str | None,
    ) -> str:
        if self._settings.mode == "local_dev":
            return supplied_project_id
        principal = self.authenticate(authorization_header)
        if principal.subject is None or not google_subject_owns_workspace_project_id(
            principal.subject,
            supplied_project_id,
        ):
            raise AuthForbiddenError(
                "Authenticated user does not own this request."
            )
        return supplied_project_id

    @staticmethod
    def _extract_bearer_token(authorization_header: str | None) -> str:
        if authorization_header is None:
            raise AuthRequiredError("Authorization bearer token is required.")
        scheme, separator, token = authorization_header.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token.strip():
            raise AuthRequiredError("Authorization bearer token is required.")
        return token.strip()
