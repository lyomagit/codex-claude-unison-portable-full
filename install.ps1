param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]] $ArgsForBootstrap
)
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Bootstrap = Join-Path $ScriptDir ".agents/skills/codex-claude-unison/scripts/bootstrap_portable.py"
$Python = $env:PYTHON
if (-not $Python) {
  if (Get-Command py -ErrorAction SilentlyContinue) { $Python = "py" }
  elseif (Get-Command python3 -ErrorAction SilentlyContinue) { $Python = "python3" }
  elseif (Get-Command python -ErrorAction SilentlyContinue) { $Python = "python" }
  else {
    Write-Error "Python 3.9+ is required. Set PYTHON to a Python executable or install py/python3/python."
    exit 1
  }
}
& $Python $Bootstrap --mode auto --target (Get-Location).Path --replace-existing --yes @ArgsForBootstrap
exit $LASTEXITCODE
