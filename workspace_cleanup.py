import argparse
import asyncio
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from google.cloud.firestore import AsyncClient

from auth import google_subject_to_workspace_project_id
from database import MemoryEngine


@dataclass(frozen=True)
class WorkspaceCleanupCandidate:
    user_id: str
    workspace_id: str
    reason: str
    preserve_workspace_document: bool


@dataclass(frozen=True)
class WorkspaceCleanupResult:
    user_id: str
    workspace_id: str
    reason: str
    status: str
    preserve_workspace_document: bool


def default_workspace_id_for_user(user_id: str) -> str:
    if user_id.startswith("google--"):
        return google_subject_to_workspace_project_id(
            user_id.removeprefix("google--")
        )
    return "agent-col"


async def discover_deleted_workspace_cleanup_candidates(
    client: object,
    *,
    user_id: str | None = None,
) -> list[WorkspaceCleanupCandidate]:
    users_ref = client.collection("users")
    if user_id is None:
        user_refs = [
            snapshot.reference async for snapshot in users_ref.stream()
        ]
    else:
        user_refs = [users_ref.document(user_id)]

    visible_by_user: dict[str, set[str]] = {}
    default_by_user: dict[str, str] = {}
    candidates: dict[
        tuple[str, str],
        WorkspaceCleanupCandidate,
    ] = {}

    def add_candidate(candidate: WorkspaceCleanupCandidate) -> None:
        candidates.setdefault(
            (candidate.user_id, candidate.workspace_id),
            candidate,
        )

    for user_ref in user_refs:
        current_user_id = user_ref.id
        default_workspace_id = default_workspace_id_for_user(current_user_id)
        default_by_user[current_user_id] = default_workspace_id
        default_tombstoned = False
        visible: set[str] = set()
        workspaces_ref = user_ref.collection("workspaces")
        async for workspace_ref in workspaces_ref.list_documents(
            page_size=200
        ):
            snapshot = await workspace_ref.get()
            workspace_id = workspace_ref.id
            if not snapshot.exists:
                if workspace_id != default_workspace_id:
                    add_candidate(
                        WorkspaceCleanupCandidate(
                            user_id=current_user_id,
                            workspace_id=workspace_id,
                            reason="orphaned_workspace_reference",
                            preserve_workspace_document=False,
                        )
                    )
                continue
            data = snapshot.to_dict()
            if not isinstance(data, Mapping):
                continue
            if workspace_id == default_workspace_id and data.get("deleted") is True:
                default_tombstoned = True
                add_candidate(
                    WorkspaceCleanupCandidate(
                        user_id=current_user_id,
                        workspace_id=workspace_id,
                        reason="default_tombstone_owned_data",
                        preserve_workspace_document=True,
                    )
                )
                continue
            if data.get("deleted") is True:
                add_candidate(
                    WorkspaceCleanupCandidate(
                        user_id=current_user_id,
                        workspace_id=workspace_id,
                        reason="deleted_non_default_workspace",
                        preserve_workspace_document=False,
                    )
                )
                continue
            if (
                data.get("workspace_id") == workspace_id
                and isinstance(data.get("display_name"), str)
            ):
                visible.add(workspace_id)
        if not default_tombstoned:
            visible.add(default_workspace_id)
        visible_by_user[current_user_id] = visible
    async for project_snapshot in client.collection("projects").stream():
        project_id = project_snapshot.id
        for current_user_id, default_workspace_id in default_by_user.items():
            if not _project_belongs_to_user_default(
                project_id,
                default_workspace_id,
            ):
                continue
            if project_id in visible_by_user[current_user_id]:
                continue
            add_candidate(
                WorkspaceCleanupCandidate(
                    user_id=current_user_id,
                    workspace_id=project_id,
                    reason=(
                        "default_tombstone_owned_data"
                        if project_id == default_workspace_id
                        else "orphaned_project_document"
                    ),
                    preserve_workspace_document=(
                        project_id == default_workspace_id
                    ),
                )
            )

    async for session_snapshot in client.collection("sessions").stream():
        data = session_snapshot.to_dict()
        if not isinstance(data, Mapping):
            continue
        session_user_id = data.get("user_id")
        project_id = data.get("project_id")
        if (
            not isinstance(session_user_id, str)
            or not isinstance(project_id, str)
            or session_user_id not in visible_by_user
            or project_id in visible_by_user[session_user_id]
        ):
            continue
        default_workspace_id = default_by_user[session_user_id]
        add_candidate(
            WorkspaceCleanupCandidate(
                user_id=session_user_id,
                workspace_id=project_id,
                reason=(
                    "default_tombstone_owned_data"
                    if project_id == default_workspace_id
                    else "orphaned_chat_session"
                ),
                preserve_workspace_document=project_id == default_workspace_id,
            )
        )

    return list(candidates.values())


async def cleanup_deleted_workspace_data(
    engine: object,
    candidates: Iterable[WorkspaceCleanupCandidate],
    *,
    apply: bool,
) -> list[WorkspaceCleanupResult]:
    results: list[WorkspaceCleanupResult] = []
    for candidate in candidates:
        if not apply:
            results.append(_result(candidate, "dry-run"))
            continue
        await engine._delete_non_default_workspace_owned_data(
            candidate.user_id,
            candidate.workspace_id,
        )
        if candidate.preserve_workspace_document:
            results.append(_result(candidate, "deleted-owned-data"))
            continue
        workspace_ref = (
            engine._client.collection("users")
            .document(candidate.user_id)
            .collection("workspaces")
            .document(candidate.workspace_id)
        )
        await workspace_ref.delete()
        results.append(_result(candidate, "deleted-owned-data-and-metadata"))
    return results


def _project_belongs_to_user_default(
    project_id: str,
    default_workspace_id: str,
) -> bool:
    return (
        project_id == default_workspace_id
        or project_id.startswith(f"{default_workspace_id}--")
    )


def _result(
    candidate: WorkspaceCleanupCandidate,
    status: str,
) -> WorkspaceCleanupResult:
    return WorkspaceCleanupResult(
        user_id=candidate.user_id,
        workspace_id=candidate.workspace_id,
        reason=candidate.reason,
        status=status,
        preserve_workspace_document=candidate.preserve_workspace_document,
    )


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Find and optionally remove Firestore data owned by deleted "
            "workspaces. Default tombstone workspace documents are preserved."
        )
    )
    parser.add_argument(
        "--user-id",
        help="Limit cleanup discovery to one internal user id.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the discovered data. Omit for dry-run output.",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Google Cloud project id. Defaults to GOOGLE_CLOUD_PROJECT.",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    _load_dotenv(Path(".env"))
    project = args.project or os.environ.get("GOOGLE_CLOUD_PROJECT")
    client = AsyncClient(project=project) if project else AsyncClient()
    engine = MemoryEngine(client)
    candidates = await discover_deleted_workspace_cleanup_candidates(
        client,
        user_id=args.user_id,
    )
    results = await cleanup_deleted_workspace_data(
        engine,
        candidates,
        apply=args.apply,
    )
    print(f"mode={'apply' if args.apply else 'dry-run'}")
    print(f"candidate_count={len(candidates)}")
    for result in results:
        print(
            "user={user_id} workspace={workspace_id} reason={reason} "
            "status={status} preserve_workspace_document={preserve}".format(
                user_id=result.user_id,
                workspace_id=result.workspace_id,
                reason=result.reason,
                status=result.status,
                preserve=result.preserve_workspace_document,
            )
        )
    close_result = engine.close()
    if hasattr(close_result, "__await__"):
        await close_result
    return 0


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
