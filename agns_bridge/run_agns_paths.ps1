# Desktop runner for the Agnes + Harness^2 experiment. Windows PowerShell.
# Usage (from the harness2 repo root):
#   powershell -NoProfile -File agnes_bridge\run_agns_paths.ps1 b      # Path B demo
#   powershell -NoProfile -File agnes_bridge\run_agns_paths.ps1 a      # Path A bridge
#   powershell -NoProfile -File agnes_bridge\run_agns_paths.ps1 all
param([ValidateSet("a","b","all")][string]$Cmd = "all")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
Set-Location $Root

# Ensure harness2 importable.
if (-not (python -c "import harness2" 2>$null)) {
    Write-Host "Installing harness2 in editable mode..."
    python -m pip install -e .
}

function Load-Bridge-Env {
    $envFile = Join-Path $Root ".agns_bridge.env"
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            $line = $line.Trim()
            if (-not $line -or $line.StartsWith("#")) { continue }
            $i = $line.IndexOf("=")
            if ($i -lt 1) { continue }
            [System.Environment]::SetEnvironmentVariable(
                $line.Substring(0, $i).Trim(), $line.Substring($i + 1).Trim())
        }
    }
}

function Path-B {
    Write-Host "=== Path B: Agnes substrate, deterministic demo (no model credentials) ==="
    python -m harness2.cli.agns_demo --output runs/agns_demo --k 2 --mode both
}

function Path-A {
    Write-Host "=== Path A: Agnes OpenAI-compatible bridge ==="
    Load-Bridge-Env
    if (-not $env:AGNES_API_URL) {
        Write-Host "AGNES_API_URL not set; bridge will 503 until you set it in .agns_bridge.env."
    } else {
        Write-Host "Bridge upstream: $env:AGNES_API_URL (auth: $($env:AGNES_AUTH_HEADER / 'bearer'))"
    }
    $host_ = $env:AGNES_PROXY_HOST / "127.0.0.1"
    $port  = $env:AGNES_PROXY_PORT / "8620"
    Write-Host "Start the bridge below; it runs in THIS shell."
    Write-Host "Then open a SECOND shell and run:"
    Write-Host "  \$env:OPENAI_BASE_URL='http://${host_}:${port}/v1'"
    Write-Host "  \$env:OPENAI_API_KEY='agnes-bridge'"
    Write-Host "  \$env:HARNESS2_SOLVER_MODEL='openai/$($env:AGNES_MODEL / 'agnes')'"
    Write-Host "  python -m harness2.cli.run_sweep --bench lab --substrate oc --k 1 --mode parallel"
    python -m agnes_bridge.agnes_openai_proxy
}

switch ($Cmd) {
    "b"   { Path-B }
    "a"   { Path-A }
    "all" { Path-B; ""; Path-A }
}
