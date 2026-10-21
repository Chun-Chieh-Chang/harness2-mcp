"""Harness2 MCP server package: exposes the harness2 CLI suite as Agnes Code extension tools.

Launch the stdio server with:

    python -m mcp_server.harness2_mcp

Register it as an Agnes Code extension in ~/.config/Agnes Code/config.yaml:

    extensions:
      harness2:
        name: "Harness2"
        cmd: python
        args: ["-m", "mcp_server.harness2_mcp"]
        enabled: true
        envs:
          "HARNESS2_REPO": "<path-to-harness2-repo>"
          "HARNESS2_RUNS_DIR": "<path-to-harness2-repo>/runs"
          "AGNES_CLI": "agnes run --headless"
        timeout: 900

Or from the CLI: `Agnes Code mcp harness2`.
"""
