param(
    [Parameter(Mandatory = $true)][string[]]$Images,
    [Parameter(Mandatory = $true)][string]$PromptFile,
    [Parameter(Mandatory = $true)][string]$OutFile,
    [string]$Model = 'gpt-6-astra'
)
# A second pair of eyes: asks Codex (ChatGPT login, no API key) to look at review frames and list
# visual defects with a strong vision model (gpt-6-astra by default). Read-only sandbox; the answer
# (its last message) is written to $OutFile.
$ErrorActionPreference = 'Continue'
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
$pkg = Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version -Descending | Select-Object -First 1
$cx = Join-Path $pkg.InstallLocation 'app\resources\codex.exe'
$proj = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$cxArgs = @('exec', '--skip-git-repo-check', '--ephemeral', '-s', 'read-only', '-C', $proj, '-m', $Model, '-o', $OutFile)
foreach ($i in $Images) { $cxArgs += @('-i', $i) }
$cxArgs += '-'
Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8 | & $cx @cxArgs 2>&1 | Select-Object -Last 5 | ForEach-Object { "$_" }
"codex exit: $LASTEXITCODE"
if (Test-Path -LiteralPath $OutFile) { "OK $OutFile" } else { "MISSING $OutFile"; exit 1 }
