import os
import re
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True), override=True)

ROLES = ("UE", "NGO", "PSYCHOLOG", "PSYCHIATRA", "TEST")


def _role_to_uuids() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for role in ROLES:
        pattern = re.compile(rf"^{role}_KEY(?:_\d+)?$")
        uuids: list[str] = []
        for name in sorted(os.environ):
            if not pattern.match(name):
                continue
            val = os.environ.get(name) or ""
            for part in val.split(","):
                token = part.strip().lower()
                if token:
                    uuids.append(token)
        if uuids:
            out[role] = uuids
    return out


def loaded_roles() -> list[str]:
    return list(_role_to_uuids().keys())


def resolve_role(secret: str) -> tuple[str, str] | None:
    secret = (secret or "").strip().lower()
    if not secret:
        return None
    for role, uuids in _role_to_uuids().items():
        if secret in uuids:
            return role, secret
    return None


def role_prefix(role: str) -> str:
    return role.lower()


def is_test_mode() -> bool:
    val = (os.getenv("TEST_MODE") or "").strip().lower()
    return val in ("1", "true", "yes", "on")
