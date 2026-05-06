import os
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True), override=True)

ROLES = ("UE", "NGO", "PSYCHOLOG", "PSYCHIATRA", "TEST")


def _role_to_uuid() -> dict[str, str]:
    out = {}
    for role in ROLES:
        val = os.getenv(f"{role}_KEY")
        if val:
            out[role] = val.strip().lower()
    return out


def loaded_roles() -> list[str]:
    return list(_role_to_uuid().keys())


def resolve_role(secret: str) -> tuple[str, str] | None:
    secret = (secret or "").strip().lower()
    if not secret:
        return None
    for role, uuid in _role_to_uuid().items():
        if secret == uuid:
            return role, uuid
    return None


def role_prefix(role: str) -> str:
    return role.lower()


def is_test_mode() -> bool:
    val = (os.getenv("TEST_MODE") or "").strip().lower()
    return val in ("1", "true", "yes", "on")
