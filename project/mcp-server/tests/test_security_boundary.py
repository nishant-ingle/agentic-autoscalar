import pytest
from app.server import mcp_server
from app.security import (
    enforce_read_only,
    validate_namespace,
    sanitize_tail_lines,
    SecurityViolationError
)


def test_enforce_read_only_blocks_mutations():
    """Verify write verbs are strictly blocked at security layer."""
    prohibited_ops = [
        "scale_deployment",
        "delete_pod",
        "patch_service",
        "create_ingress",
        "exec_command",
        "restart_workload"
    ]
    for op in prohibited_ops:
        with pytest.raises(SecurityViolationError) as exc_info:
            enforce_read_only(op)
        assert "WriteOperationForbidden" in str(exc_info.value)


def test_enforce_read_only_permits_reads():
    """Verify safe read-only operations pass through without exception."""
    safe_ops = [
        "get_cluster_metrics",
        "fetch_recent_logs",
        "query_prometheus_range",
        "read_telemetry"
    ]
    for op in safe_ops:
        # Should not raise exception
        enforce_read_only(op)


def test_namespace_validation_restricts_unauthorized_probes():
    """Verify sensitive or unlisted namespaces are rejected."""
    # Permitted namespaces
    assert validate_namespace("workload-system") == "workload-system"
    assert validate_namespace("default") == "default"

    # Restricted namespaces
    with pytest.raises(SecurityViolationError) as exc_info:
        validate_namespace("kube-system")
    assert "UnauthorizedNamespace" in str(exc_info.value)

    # Malformed names
    with pytest.raises(SecurityViolationError):
        validate_namespace("../escape")


def test_sanitize_tail_lines():
    """Verify log tail lines are bounded between 1 and 200."""
    assert sanitize_tail_lines(50) == 50
    assert sanitize_tail_lines(500) == 200
    assert sanitize_tail_lines(-5) == 10


@pytest.mark.asyncio
async def test_mcp_execute_cluster_action_tool_blocks_write():
    """Verify MCP tool call with write verb returns blocked security status."""
    res = await mcp_server.call_tool(
        name="execute_cluster_action",
        arguments={"action": "scale_deployment_to_10", "target": "target-workload"}
    )
    assert not res.is_error
    data = res.structured_content.get("result", res.structured_content)
    assert data.get("status") == "blocked"
    assert data.get("is_forbidden") is True
    assert "WriteOperationForbidden" in data.get("security_error", "")
