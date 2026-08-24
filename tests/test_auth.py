import pytest

from auth import (
    AuthConfigurationError,
    AuthForbiddenError,
    AuthRequiredError,
    AuthSettings,
    Authenticator,
    google_subject_owns_workspace_project_id,
    google_subject_to_workspace_project_id,
)


def test_local_development_auth_uses_supplied_user_without_token() -> None:
    authenticator = Authenticator(AuthSettings(mode="local_dev"))

    assert authenticator.resolve_user_id(
        supplied_user_id="wifiknight",
        authorization_header=None,
    ) == "wifiknight"


def test_google_oidc_requires_bearer_token() -> None:
    authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123")
    )

    with pytest.raises(AuthRequiredError):
        authenticator.authenticate(None)

    with pytest.raises(AuthRequiredError):
        authenticator.authenticate("Basic not-a-google-token")


def test_google_oidc_verifies_token_and_derives_stable_user_id() -> None:
    verifier_calls = []

    def verify_token(token: str, client_id: str) -> dict[str, object]:
        verifier_calls.append((token, client_id))
        return {
            "sub": "109876543210",
            "email": "user@example.com",
            "name": "WiFi Knight",
        }

    authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=verify_token,
    )

    principal = authenticator.authenticate("Bearer token-abc")

    assert verifier_calls == [("token-abc", "client-123")]
    assert principal.authenticated is True
    assert principal.provider == "google_oidc"
    assert principal.subject == "109876543210"
    assert principal.user_id == "google--109876543210"
    assert principal.workspace_project_id == (
        google_subject_to_workspace_project_id("109876543210")
    )
    assert "109876543210" not in principal.workspace_project_id
    assert principal.email == "user@example.com"
    assert principal.display_name == "WiFi Knight"


def test_google_oidc_rejects_request_user_mismatch() -> None:
    authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": "109876543210"},
    )

    with pytest.raises(AuthForbiddenError):
        authenticator.resolve_user_id(
            supplied_user_id="attacker",
            authorization_header="Bearer token-abc",
        )


def test_google_oidc_rejects_project_mismatch() -> None:
    authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": "109876543210"},
    )
    owned_project_id = google_subject_to_workspace_project_id("109876543210")

    assert authenticator.resolve_project_id(
        supplied_project_id=owned_project_id,
        authorization_header="Bearer token-abc",
    ) == owned_project_id

    with pytest.raises(AuthForbiddenError):
        authenticator.resolve_project_id(
            supplied_project_id="agent-col",
            authorization_header="Bearer token-abc",
        )


def test_google_oidc_accepts_owned_secondary_workspace_project_ids() -> None:
    authenticator = Authenticator(
        AuthSettings(mode="google_oidc", google_client_id="client-123"),
        token_verifier=lambda token, client_id: {"sub": "109876543210"},
    )
    default_project_id = google_subject_to_workspace_project_id("109876543210")
    owned_workspace_id = f"{default_project_id}--study-plans"

    assert google_subject_owns_workspace_project_id(
        "109876543210",
        owned_workspace_id,
    )
    assert authenticator.resolve_project_id(
        supplied_project_id=owned_workspace_id,
        authorization_header="Bearer token-abc",
    ) == owned_workspace_id

    with pytest.raises(AuthForbiddenError):
        authenticator.resolve_project_id(
            supplied_project_id="project--other-subject--study-plans",
            authorization_header="Bearer token-abc",
        )


def test_google_oidc_requires_configured_client_id() -> None:
    authenticator = Authenticator(AuthSettings(mode="google_oidc"))

    with pytest.raises(AuthConfigurationError):
        authenticator.authenticate("Bearer token-abc")
