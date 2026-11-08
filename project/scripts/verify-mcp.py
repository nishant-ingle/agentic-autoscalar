#!/usr/bin/env python3
"""Automated Acceptance Verification Script for Epic 4 (MCP Server).

Verifies modern Streamable HTTP transport (/mcp) as primary, along with
backward-compatible SSE transport (/sse), dynamic tool discovery, tool
execution, and read-only security boundaries.
"""
import asyncio
import sys
import json
import httpx
from mcp.client.streamable_http import streamable_http_client
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

MCP_BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
STREAMABLE_URL = f"{MCP_BASE_URL.rstrip('/')}/mcp"
SSE_URL = f"{MCP_BASE_URL.rstrip('/')}/sse"


async def run_verification():
    print("==========================================================")
    print(" [Acceptance Verification] Checking Epic 4 MCP Server Layer")
    print(f" MCP Server URL: {MCP_BASE_URL}")
    print(f" Modern Streamable HTTP Endpoint: {STREAMABLE_URL}")
    print(f" Legacy SSE Endpoint:            {SSE_URL}")
    print("==========================================================")

    # -------------------------------------------------------------------------
    # Check 1: REST Health & Metadata Info Probes
    # -------------------------------------------------------------------------
    print("\n[Check 1/5] Verifying REST Health & Info Endpoints...")
    async with httpx.AsyncClient(timeout=10.0) as http_client:
        try:
            health_resp = await http_client.get(f"{MCP_BASE_URL}/healthz")
            health_resp.raise_for_status()
            health_data = health_resp.json()
            assert health_data.get("status") == "UP"
            print(f"✔ Health probe passed: status={health_data.get('status')}, transports={health_data.get('transports')}")

            info_resp = await http_client.get(f"{MCP_BASE_URL}/info")
            info_resp.raise_for_status()
            info_data = info_resp.json()
            assert info_data.get("tools_count", 0) >= 4
            print(f"✔ Info probe passed: primary={info_data.get('primary_transport')}, registered tools={info_data.get('tools_count')}")
        except Exception as exc:
            print(f"✖ Failed REST probe check: {exc}")
            sys.exit(1)

    # -------------------------------------------------------------------------
    # Check 2: Modern Streamable HTTP Handshake & Dynamic Tool Discovery
    # -------------------------------------------------------------------------
    print("\n[Check 2/5] Verifying Modern Streamable HTTP Handshake & Tool Discovery (tools/list)...")
    try:
        async with streamable_http_client(STREAMABLE_URL) as (read, write):
            async with ClientSession(read, write) as session:
                init_res = await session.initialize()
                print(f"✔ Streamable HTTP initialized: server='{init_res.server_info.name}', version='{init_res.server_info.version}'")

                tools_res = await session.list_tools()
                tool_names = [t.name for t in tools_res.tools]
                print(f"✔ Discovered tools ({len(tool_names)}): {tool_names}")

                assert "get_cluster_metrics" in tool_names, "Missing get_cluster_metrics"
                assert "query_prometheus_range" in tool_names, "Missing query_prometheus_range"
                assert "fetch_recent_logs" in tool_names, "Missing fetch_recent_logs"
                assert "execute_cluster_action" in tool_names, "Missing execute_cluster_action"
                print("✔ All required MCP tool definitions successfully registered.")

                # -------------------------------------------------------------------------
                # Check 3: Modern Streamable HTTP Tool Execution (tools/call)
                # -------------------------------------------------------------------------
                print("\n[Check 3/5] Verifying Modern Streamable HTTP Tool Execution (tools/call)...")
                # 3a. get_cluster_metrics
                metrics_res = await session.call_tool(
                    "get_cluster_metrics",
                    {"namespace": "workload-system", "workload_name": "target-workload"}
                )
                assert not metrics_res.is_error, "get_cluster_metrics returned error"
                metrics_data = (metrics_res.structured_content or {}).get("result", metrics_res.structured_content)
                print(f"✔ Tool 'get_cluster_metrics' executed successfully:")
                print(f"   Status: {metrics_data.get('status')} | Ready Replicas: {metrics_data.get('ready_replicas')} | Pods: {len(metrics_data.get('pods', []))}")

                # 3b. fetch_recent_logs
                logs_res = await session.call_tool(
                    "fetch_recent_logs",
                    {"namespace": "workload-system", "workload_name": "target-workload", "tail_lines": 5}
                )
                assert not logs_res.is_error, "fetch_recent_logs returned error"
                logs_data = (logs_res.structured_content or {}).get("result", logs_res.structured_content)
                print(f"✔ Tool 'fetch_recent_logs' executed successfully:")
                print(f"   Status: {logs_data.get('status')} | Pods Sampled: {logs_data.get('pods_sampled', 0)}")

                # -------------------------------------------------------------------------
                # Check 4: Strict Read-Only Security Boundary Enforcement
                # -------------------------------------------------------------------------
                print("\n[Check 4/5] Verifying Strict Read-Only Security Boundary Enforcement...")
                sec_res = await session.call_tool(
                    "execute_cluster_action",
                    {"action": "scale_deployment_to_10", "target": "target-workload"}
                )
                sec_data = (sec_res.structured_content or {}).get("result", sec_res.structured_content)
                if sec_data.get("status") == "blocked" and sec_data.get("is_forbidden") is True:
                    print(f"✔ Security boundary successfully blocked prohibited write operation:")
                    print(f"   Reason: {sec_data.get('security_error')}")
                else:
                    print(f"✖ Security boundary failed! Mutating action was not blocked: {sec_data}")
                    sys.exit(1)

    except Exception as exc:
        print(f"✖ Modern Streamable HTTP session failed: {exc}")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Check 5: Backward-Compatible Legacy SSE Transport Handshake
    # -------------------------------------------------------------------------
    print("\n[Check 5/5] Verifying Legacy SSE Transport Backward Compatibility (/sse)...")
    try:
        async with sse_client(SSE_URL) as (read, write):
            async with ClientSession(read, write) as session:
                init_res = await session.initialize()
                print(f"✔ Legacy SSE initialized: server='{init_res.server_info.name}'")
                tools_res = await session.list_tools()
                assert len(tools_res.tools) >= 4
                print(f"✔ Legacy SSE tool listing confirmed ({len(tools_res.tools)} tools)")
    except Exception as exc:
        print(f"✖ Legacy SSE session failed: {exc}")
        sys.exit(1)

    print("\n==========================================================")
    print(" ALL EPIC 4 ACCEPTANCE CRITERIA SUCCESSFULLY VERIFIED! ✔")
    print(" (Modern Streamable HTTP & Legacy SSE Both Operational)   ")
    print("==========================================================")


if __name__ == "__main__":
    asyncio.run(run_verification())
