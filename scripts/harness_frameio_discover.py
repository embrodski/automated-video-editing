#!/usr/bin/env python3
"""Discover Frame.io account and upload folder IDs after OAuth login."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from frameio_client import FRAMEIO_API_BASE, _api_request
from frameio_oauth import PIAB_DEFAULTS, get_valid_access_token
from harness_env import DEFAULT_ENV_PATH, load_harness_env, merge_env_file

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(str(value or "").strip()))


def _pick_account(accounts: list[dict]) -> dict:
    if not accounts:
        raise RuntimeError("No Frame.io accounts returned for this user.")
    if len(accounts) == 1:
        return accounts[0]
    print("Multiple Frame.io accounts found:")
    for i, item in enumerate(accounts, start=1):
        label = item.get("display_name") or item.get("name") or item.get("id")
        print(f"  {i}. {label} ({item.get('id')})")
    while True:
        raw = input("Choose account number [1]: ").strip() or "1"
        if raw.isdigit() and 1 <= int(raw) <= len(accounts):
            return accounts[int(raw) - 1]
        print("Enter a valid number.")


def _list_projects(*, account_id: str, token: str) -> list[dict]:
    projects: list[dict] = []
    url: str | None = f"{FRAMEIO_API_BASE}/accounts/{account_id}/projects?page_size=100"
    while url:
        response = _api_request("GET", url, token=token)
        batch = response.get("data") or []
        if isinstance(batch, list):
            projects.extend(item for item in batch if isinstance(item, dict))
        links = response.get("links") or {}
        url = links.get("next") if isinstance(links, dict) else None
    return projects


def _pick_project(projects: list[dict]) -> dict:
    if not projects:
        raise RuntimeError("No Frame.io projects found for this account.")
    print("Frame.io projects:")
    for i, item in enumerate(projects, start=1):
        label = item.get("name") or item.get("title") or item.get("id")
        print(f"  {i}. {label} ({item.get('id')})")
    while True:
        raw = input("Choose project number [1]: ").strip() or "1"
        if raw.isdigit() and 1 <= int(raw) <= len(projects):
            return projects[int(raw) - 1]
        print("Enter a valid number.")


def _find_project(
    *,
    account_id: str,
    token: str,
    project_id: str,
    project_name: str,
) -> dict:
    project_id = str(project_id or "").strip()
    project_name = str(project_name or "").strip()

    if project_id and _is_uuid(project_id):
        project_url = f"{FRAMEIO_API_BASE}/accounts/{account_id}/projects/{project_id}"
        project_resp = _api_request("GET", project_url, token=token)
        project = project_resp.get("data")
        if isinstance(project, dict):
            return project
        raise RuntimeError(f"Could not load project {project_id}.")

    projects = _list_projects(account_id=account_id, token=token)
    if project_name:
        exact = [
            project
            for project in projects
            if str(project.get("name") or project.get("title") or "").strip()
            == project_name
        ]
        if len(exact) == 1:
            return exact[0]
        needle = project_name.casefold()
        fuzzy = [
            project
            for project in projects
            if needle in str(project.get("name") or project.get("title") or "").casefold()
        ]
        if len(fuzzy) == 1:
            return fuzzy[0]
        if len(fuzzy) > 1:
            print(f"Multiple projects matched {project_name!r}:")
            for i, project in enumerate(fuzzy, start=1):
                label = project.get("name") or project.get("title") or project.get("id")
                print(f"  {i}. {label} ({project.get('id')})")
            while True:
                raw = input("Choose project number [1]: ").strip() or "1"
                if raw.isdigit() and 1 <= int(raw) <= len(fuzzy):
                    return fuzzy[int(raw) - 1]
                print("Enter a valid number.")

    if project_id and not _is_uuid(project_id):
        print(
            f"WARNING: {project_id!r} is an App Builder id, not a Frame.io project UUID.",
            file=sys.stderr,
        )
    if project_name:
        print(
            f"WARNING: No Frame.io project named {project_name!r} was found.",
            file=sys.stderr,
        )
        print(
            "Create that project in Frame.io first, or choose an existing project below.",
            file=sys.stderr,
        )
    return _pick_project(projects)


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover Frame.io IDs for PIAB delivery.")
    parser.add_argument(
        "--project-id",
        default="",
        help="Frame.io project UUID. If omitted, search by --project-name.",
    )
    parser.add_argument(
        "--project-name",
        default=PIAB_DEFAULTS["project_name"],
        help="Frame.io project name to match when --project-id is not a UUID.",
    )
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Write discovered IDs into repo-root .env",
    )
    args = parser.parse_args()

    load_harness_env()
    token = get_valid_access_token()
    if not token:
        print(
            "ERROR: No Frame.io OAuth token. Run: python scripts/harness_frameio_oauth.py login",
            file=sys.stderr,
        )
        return 1

    accounts_resp = _api_request("GET", f"{FRAMEIO_API_BASE}/accounts", token=token)
    accounts = accounts_resp.get("data") or []
    if not isinstance(accounts, list):
        raise RuntimeError("Unexpected /accounts response.")
    account = _pick_account([a for a in accounts if isinstance(a, dict)])
    account_id = str(account["id"])

    project = _find_project(
        account_id=account_id,
        token=token,
        project_id=str(args.project_id or ""),
        project_name=str(args.project_name or ""),
    )
    project_id = str(project["id"])

    upload_folder_id = str(
        project.get("root_folder_id")
        or project.get("folder_id")
        or project.get("id")
        or ""
    ).strip()
    if not upload_folder_id:
        raise RuntimeError("Project response did not include root_folder_id.")

    result = {
        "account_id": account_id,
        "project_id": project_id,
        "upload_folder_id": upload_folder_id,
        "project_name": project.get("name") or project.get("title"),
        "account_name": account.get("display_name") or account.get("name"),
    }
    print(json.dumps(result, indent=2))

    if args.write_env:
        merge_env_file(
            DEFAULT_ENV_PATH,
            {
                "FRAMEIO_ACCOUNT_ID": account_id,
                "FRAMEIO_PROJECT_ID": project_id,
                "FRAMEIO_UPLOAD_FOLDER_ID": upload_folder_id,
                "FRAMEIO_CLIENT_ID": PIAB_DEFAULTS["client_id"],
            },
        )
        print(f"\nWrote Frame.io IDs to {DEFAULT_ENV_PATH}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
