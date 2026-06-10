<# 
.SYNOPSIS
    Elimina ramas locales cuyo remote ya no existe (gone).
.DESCRIPTION
    1. Hace git fetch --prune para actualizar el estado de los remotes
    2. Identifica ramas con upstream "gone"
    3. Las borra con -D (squash merges make -d fail)
#>

param(
    [switch]$DryRun
)

Write-Host ""
Write-Host "[*] Fetching and pruning remotes..." -ForegroundColor Cyan
git fetch --prune

$goneBranches = git branch -vv | Where-Object { $_ -match ": gone\]" } | ForEach-Object {
    ($_ -replace "^\*?\s+", "") -split "\s+" | Select-Object -First 1
}

if (-not $goneBranches -or $goneBranches.Count -eq 0) {
    Write-Host "[OK] No hay ramas locales con remote eliminado." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "[i] Ramas locales sin remote ($($goneBranches.Count)):" -ForegroundColor Yellow
$goneBranches | ForEach-Object { Write-Host "   - $_" -ForegroundColor Gray }

if ($DryRun) {
    Write-Host ""
    Write-Host "[!] Dry run - no se borro nada." -ForegroundColor Yellow
    exit 0
}

Write-Host ""

foreach ($branch in $goneBranches) {
    Write-Host "[x] Eliminando $branch... " -NoNewline
    
    $result = git branch -D $branch 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK" -ForegroundColor Green
    } else {
        Write-Host "ERROR" -ForegroundColor Red
        Write-Host "    $result" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "[OK] Limpieza completada." -ForegroundColor Green
