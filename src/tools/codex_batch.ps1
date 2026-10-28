param(
    [Parameter(Mandatory = $true)][string[]]$Names,
    [string]$Version = 'v1',
    [string[]]$RefImages = @()
)
# Runs codex_image.ps1 once per prompt name, skipping outputs that already exist.
$ErrorActionPreference = 'Continue'
$proj = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
# every pose is drawn from the turnaround sheet, so the character stays the same across poses
if ($RefImages.Count -eq 0) { $RefImages = @(Join-Path $proj 'assets\char\raw\rin_ref_sheet_v2.png') }
foreach ($n in $Names) {
    $out = Join-Path $proj "assets\char\raw\${n}_$Version.png"
    if (Test-Path -LiteralPath $out) { "skip $n"; continue }
    $log = Join-Path $proj "work\codex_${n}_$Version.log"
    & (Join-Path $proj 'src\tools\codex_image.ps1') -PromptFile (Join-Path $proj "assets\char\prompts\$n.txt") -OutPath $out -RefImages $RefImages *> $log
    if (Test-Path -LiteralPath $out) { "done $n" } else { "FAILED $n (see $log)" }
}
