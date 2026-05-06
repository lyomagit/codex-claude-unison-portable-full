param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]] $ArgsForBootstrap
)
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Bootstrap = Join-Path $ScriptDir ".agents/skills/codex-claude-unison/scripts/bootstrap_portable.py"
$Python = $env:PYTHON
if (-not $Python) { $Python = "py" }
& $Python $Bootstrap --mode auto --target (Get-Location).Path --replace-existing --yes @ArgsForBootstrap
exit $LASTEXITCODE
