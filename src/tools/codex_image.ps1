param(
    [Parameter(Mandatory = $true)][string]$PromptFile,
    [Parameter(Mandatory = $true)][string]$OutPath,
    [string[]]$RefImages = @()
)
# Generates one image with the Codex built-in image_gen tool (ChatGPT login, no API key).
# The API key is removed from this process so Codex can never use it for model calls.
# Native stderr is expected (progress lines), so errors are judged by exit code and output file.
$ErrorActionPreference = 'Continue'
Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
# the Codex app updates itself, so find the installed version instead of a fixed path
$pkg = Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version -Descending | Select-Object -First 1
$cx = Join-Path $pkg.InstallLocation 'app\resources\codex.exe'
$proj = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$spec = Get-Content -LiteralPath $PromptFile -Raw -Encoding UTF8
$refNote = ''
if ($RefImages.Count -gt 0) {
    $refNote = "The attached image(s) are REFERENCE images for the character design (identity, hair, outfit, colors, line style). Keep the character identical to them.`n"
}
$instr = @"
Use the built-in image_gen tool exactly once to create the image described below. Do not use scripts/image_gen.py, any API key, or any other image tool. Do not create or edit any other files.
$refNote
After generating, copy the generated PNG (keep its alpha channel if present) to this exact path, creating folders as needed:
$OutPath
Then reply with only the final path.

IMAGE SPEC:
$spec
"@
$cxArgs = @('exec', '--skip-git-repo-check', '--ephemeral', '-s', 'workspace-write', '-C', $proj)
foreach ($r in $RefImages) { $cxArgs += @('-i', $r) }
$cxArgs += '-'
$instr | & $cx @cxArgs 2>&1 | ForEach-Object { "$_" }
"codex exit: $LASTEXITCODE"
if (Test-Path -LiteralPath $OutPath) { "OK $OutPath" } else { "MISSING $OutPath"; exit 1 }
