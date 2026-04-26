"""FastAPI dashboard for observability and monitoring.

Per plan.md §8.6: Single-file HTML dashboard showing traces, spans, judge verdicts,
memory stats, and rate limit status.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

__all__ = ["DashboardApp"]


def create_dashboard_html(
    traces_data: list[dict[str, Any]],
    memory_stats: dict[str, Any],
    rate_limit_status: dict[str, Any],
) -> str:
    """Generate standalone HTML dashboard."""
    traces_json = json.dumps(traces_data)
    memory_json = json.dumps(memory_stats)
    ratelimit_json = json.dumps(rate_limit_status)

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Multi-Persona Voice Agent Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5;
            color: #333;
        }}
        header {{
            background: #2c3e50;
            color: white;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        header h1 {{
            font-size: 24px;
        }}
        header p {{
            font-size: 12px;
            opacity: 0.8;
        }}
        .container {{
            max-width: 1400px;
            margin: 20px auto;
            padding: 0 20px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .card h2 {{
            font-size: 18px;
            margin-bottom: 15px;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 10px;
        }}
        .metric {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #f0f0f0;
        }}
        .metric:last-child {{
            border-bottom: none;
        }}
        .metric-label {{
            font-weight: 500;
        }}
        .metric-value {{
            font-size: 18px;
            font-weight: bold;
            color: #2c3e50;
        }}
        .status-ok {{ color: #27ae60; }}
        .status-warn {{ color: #f39c12; }}
        .status-error {{ color: #e74c3c; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #f0f0f0;
        }}
        th {{
            background: #f9f9f9;
            font-weight: 600;
        }}
        tr:hover {{
            background: #fafafa;
        }}
        .timestamp {{
            font-size: 12px;
            color: #999;
        }}
        footer {{
            text-align: center;
            padding: 20px;
            color: #999;
            font-size: 12px;
            margin-top: 40px;
        }}
        .refresh-btn {{
            background: #3498db;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
        }}
        .refresh-btn:hover {{
            background: #2980b9;
        }}
    </style>
</head>
<body>
    <header>
        <h1>Multi-Persona Voice Agent</h1>
        <p>Observability Dashboard | Last updated: {{now}}</p>
    </header>

    <div class="container">
        <div style="text-align: right; margin-bottom: 20px;">
            <button class="refresh-btn" onclick="location.reload()">Refresh</button>
        </div>

        <div class="grid">
            <!-- Traces Overview -->
            <div class="card">
                <h2>Recent Traces</h2>
                <div id="traces-summary"></div>
            </div>

            <!-- Memory Stats -->
            <div class="card">
                <h2>Memory Usage</h2>
                <div id="memory-stats"></div>
            </div>

            <!-- Rate Limits -->
            <div class="card">
                <h2>Rate Limiting</h2>
                <div id="ratelimit-status"></div>
            </div>
        </div>

        <!-- Detailed Traces Table -->
        <div class="card">
            <h2>Execution Traces (Last 20)</h2>
            <table id="traces-table">
                <thead>
                    <tr>
                        <th>Trace ID</th>
                        <th>Persona</th>
                        <th>Role</th>
                        <th>Output Tokens</th>
                        <th>Error</th>
                        <th>Timestamp</th>
                    </tr>
                </thead>
                <tbody id="traces-body"></tbody>
            </table>
        </div>
    </div>

    <footer>
        <p>Multi-Persona Voice Agent | Batch 2 Dashboard</p>
    </footer>

    <script>
        const tracesData = {traces_json};
        const memoryStats = {memory_json};
        const rateLimitStatus = {ratelimit_json};

        function formatTimestamp(ts) {{
            return new Date(ts * 1000).toLocaleString();
        }}

        function renderTracesSummary() {{
            const summary = document.getElementById('traces-summary');
            const totalTraces = tracesData.length;
            const errorTraces = tracesData.filter(t => t.error).length;
            const avgTokens = tracesData.length > 0
                ? (tracesData.reduce((sum, t) => sum + t.output_tokens, 0) / tracesData.length).toFixed(0)
                : 0;

            summary.innerHTML = `
                <div class="metric">
                    <span class="metric-label">Total Traces</span>
                    <span class="metric-value">${{totalTraces}}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Errors</span>
                    <span class="metric-value status-${{errorTraces > 0 ? 'error' : 'ok'}}">${{errorTraces}}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Avg Tokens</span>
                    <span class="metric-value">${{avgTokens}}</span>
                </div>
            `;
        }}

        function renderMemoryStats() {{
            const memory = document.getElementById('memory-stats');
            const stats = memoryStats || {{}};
            const sessions = stats.sessions || 0;
            const episodes = stats.episodes || 0;
            const dreams = stats.dreams || 0;

            memory.innerHTML = `
                <div class="metric">
                    <span class="metric-label">Sessions</span>
                    <span class="metric-value">${{sessions}}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Episodes (L2)</span>
                    <span class="metric-value">${{episodes}}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Dreams (L3)</span>
                    <span class="metric-value">${{dreams}}</span>
                </div>
            `;
        }}

        function renderRateLimitStatus() {{
            const rateLimit = document.getElementById('ratelimit-status');
            const status = rateLimitStatus || {{}};
            const limitedCount = status.limited_count || 0;
            const statusClass = limitedCount > 0 ? 'status-warn' : 'status-ok';

            rateLimit.innerHTML = `
                <div class="metric">
                    <span class="metric-label">Currently Limited</span>
                    <span class="metric-value ${{statusClass}}">${{limitedCount}}</span>
                </div>
            `;
        }}

        function renderTracesTable() {{
            const tbody = document.getElementById('traces-body');
            tbody.innerHTML = tracesData.map(trace => `
                <tr>
                    <td><code>${{trace.trace_id.substring(0, 12)}}...</code></td>
                    <td>${{trace.persona}}</td>
                    <td><span style="background: #e8f4f8; padding: 2px 6px; border-radius: 3px;">${{trace.role}}</span></td>
                    <td>${{trace.output_tokens}}</td>
                    <td><span class="status-${{trace.error ? 'error' : 'ok'}}">${{trace.error ? '✗' : '✓'}}</span></td>
                    <td class="timestamp">${{formatTimestamp(trace.timestamp)}}</td>
                </tr>
            `).join('');
        }}

        // Initial render
        renderTracesSummary();
        renderMemoryStats();
        renderRateLimitStatus();
        renderTracesTable();
    </script>
</body>
</html>
"""


class DashboardApp:
    """Wrapper for FastAPI dashboard integration."""

    def __init__(self, tracer: Any = None, memory_store: Any = None):
        """Initialize dashboard.

        Args:
            tracer: Tracer instance for trace data
            memory_store: MemoryStore instance for memory stats
        """
        self.tracer = tracer
        self.memory_store = memory_store

    def render_html(self) -> str:
        """Render dashboard HTML with current data."""
        # Gather data
        traces_data = []
        memory_stats = {}
        rate_limit_status = {}

        if self.tracer:
            # Sample recent traces (from all personas)
            # In real usage, this would query recent traces from tracer
            traces_data = []

        if self.memory_store:
            # Memory stats placeholder
            memory_stats = {"sessions": 0, "episodes": 0, "dreams": 0}

        now = datetime.now(timezone.utc).isoformat()
        return create_dashboard_html(traces_data, memory_stats, rate_limit_status).replace(
            "{{now}}", now
        )

    # When integrated with FastAPI, this would be used like:
    # @app.get("/dashboard")
    # def get_dashboard():
    #     return HTMLResponse(dashboard.render_html())
