import logging
import re
from typing import Set
from app.config import settings

logger = logging.getLogger(__name__)

PROHIBITED_WRITE_VERBS: Set[str] = {
    "create", "apply", "patch", "scale", "delete", "destroy",
    "update", "edit", "exec", "drain", "cordon", "kill",
    "modify", "write", "truncate", "drop", "restart"
}


class SecurityViolationError(Exception):
    """Raised when an operation breaches the MCP Server security boundary."""
    pass


def enforce_read_only(operation: str) -> None:
    """Enforces that only strictly read-only actions are permitted.
    
    Raises:
        SecurityViolationError: If a mutating or write action is attempted.
    """
    op_lower = operation.strip().lower()
    for verb in PROHIBITED_WRITE_VERBS:
        # Match exact word or prefix like scale_down, patch_resource, delete_pod
        if re.search(rf"\b{verb}\b", op_lower) or op_lower.startswith(f"{verb}_") or op_lower.startswith(f"{verb}-"):
            logger.error("SECURITY BOUNDARY BREACH: Blocked prohibited write operation '%s'", operation)
            raise SecurityViolationError(
                f"WriteOperationForbidden: MCP server enforces strict read-only security. "
                f"Operation '{operation}' containing prohibited action '{verb}' was rejected."
            )


def validate_namespace(namespace: str) -> str:
    """Validates that target namespace is permitted by security policy.
    
    Raises:
        SecurityViolationError: If namespace is unauthorized or malformed.
    """
    if not namespace or not re.match(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$", namespace):
        raise SecurityViolationError(f"InvalidNamespace: Namespace '{namespace}' contains invalid characters.")

    if settings.allowed_namespaces and namespace not in settings.allowed_namespaces:
        logger.warning("Namespace '%s' is not in allowed list: %s", namespace, settings.allowed_namespaces)
        raise SecurityViolationError(
            f"UnauthorizedNamespace: Namespace '{namespace}' is restricted. "
            f"Allowed namespaces: {settings.allowed_namespaces}"
        )

    return namespace


def sanitize_tail_lines(tail_lines: int) -> int:
    """Bounds log tailing to prevent excessive memory allocation."""
    if tail_lines <= 0:
        return 10
    if tail_lines > settings.max_log_lines:
        logger.info("Clamping requested tail_lines %d to security ceiling %d", tail_lines, settings.max_log_lines)
        return settings.max_log_lines
    return tail_lines
