<#
.SYNOPSIS
    Empaqueta los commits exclusivos de una rama en un bundle de Git,
    lo convierte a Base64 y lo divide en trozos de N lineas.

.DESCRIPTION
    1. Crea <branch>.bundle con solo los commits de la rama respecto a main
       (usa main..<branch> para minimizar el tamano del fichero).
    2. Verifica el bundle con git bundle verify.
    3. Convierte el bundle a Base64 y lo divide en trozos de <ChunkLines> lineas,
       generando <branch>.bundle.b64.001, .002, ...
    4. Imprime instrucciones para reconstruir el bundle en el entorno destino.

.PARAMETER Branch
    Nombre de la rama a empaquetar. Por defecto: rama actual.

.PARAMETER Base
    Rama base contra la que se calculan los commits exclusivos. Por defecto: main.

.PARAMETER ChunkLines
    Numero de lineas por trozo de Base64. Por defecto: 1000.

.PARAMETER OutputDir
    Directorio de salida. Por defecto: directorio raiz del repositorio.

.EXAMPLE
    .\script\bundle-branch.ps1
    .\script\bundle-branch.ps1 -Branch feat/99and100
    .\script\bundle-branch.ps1 -Branch feat/99and100 -ChunkLines 500
#>

param(
    [string]$Branch    = "",
    [string]$Base      = "main",
    [int]   $ChunkLines = 1000,
    [string]$OutputDir = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── Resolve branch ────────────────────────────────────────────────────────────
if (-not $Branch) {
    $Branch = git rev-parse --abbrev-ref HEAD 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Error "No se pudo obtener la rama actual. Ejecuta desde dentro del repositorio."
        exit 1
    }
}

if ($Branch -eq $Base) {
    Write-Error "La rama '$Branch' es la misma que la base '$Base'. Cambia a una rama de feature."
    exit 1
}

# ── Resolve output dir ────────────────────────────────────────────────────────
if (-not $OutputDir) {
    $OutputDir = git rev-parse --show-toplevel 2>&1
    if ($LASTEXITCODE -ne 0) { $OutputDir = "." }
}

# Nombre de fichero: sustituir '/' por '-' para evitar subdirectorios
$SafeName   = $Branch -replace "[/\\]", "-"
$BundlePath = Join-Path $OutputDir "$SafeName.bundle"
$B64Path    = "$BundlePath.b64"

# ── Commits exclusivos ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[*] Rama:  $Branch" -ForegroundColor Cyan
Write-Host "[*] Base:  $Base"   -ForegroundColor Cyan

$commits = git log --oneline "$Base..$Branch" 2>&1
if ($LASTEXITCODE -ne 0 -or -not $commits) {
    Write-Host "[!] No hay commits exclusivos en '$Branch' respecto a '$Base'." -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "[i] Commits incluidos en el bundle:" -ForegroundColor Yellow
$commits | ForEach-Object { Write-Host "   $_" -ForegroundColor Gray }

# ── Crear bundle ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[*] Creando bundle: $BundlePath" -ForegroundColor Cyan
git bundle create $BundlePath "$Base..$Branch"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Error al crear el bundle."
    exit 1
}

$bundleSize = [math]::Round((Get-Item $BundlePath).Length / 1KB, 1)
Write-Host "[OK] Bundle creado ($bundleSize KB)" -ForegroundColor Green

# ── Verificar bundle ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[*] Verificando bundle..." -ForegroundColor Cyan
# git bundle verify sends all output to stderr. Capture via cmd /c to avoid
# PowerShell treating stderr ErrorRecords as terminating errors.
$verifyOut = cmd /c "git bundle verify `"$BundlePath`" 2>&1"
$verifyOk  = ($LASTEXITCODE -eq 0)
$verifyOut | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
if (-not $verifyOk) {
    Write-Error "El bundle no pasa la verificacion."
    exit 1
}
Write-Host "[OK] Bundle verificado" -ForegroundColor Green

# ── Convertir a Base64 ────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[*] Convirtiendo a Base64..." -ForegroundColor Cyan
$bytes  = [System.IO.File]::ReadAllBytes($BundlePath)
$b64    = [System.Convert]::ToBase64String($bytes)
$lines  = $b64 -split "(.{76})" | Where-Object { $_ -ne "" }   # 76 chars/line = standard Base64

# Dividir en trozos de ChunkLines lineas
$chunks    = [math]::Ceiling($lines.Count / $ChunkLines)
$padWidth  = $chunks.ToString().Length
$chunkFiles = @()

for ($i = 0; $i -lt $chunks; $i++) {
    $start     = $i * $ChunkLines
    $end       = [math]::Min($start + $ChunkLines - 1, $lines.Count - 1)
    $chunkNum  = ($i + 1).ToString().PadLeft($padWidth, "0")
    $chunkFile = "$B64Path.$chunkNum"
    $lines[$start..$end] | Set-Content -Path $chunkFile -Encoding ascii
    $chunkFiles += $chunkFile
    $chunkKB = [math]::Round((Get-Item $chunkFile).Length / 1KB, 1)
    Write-Host "   Trozo $chunkNum/$chunks -> $(Split-Path $chunkFile -Leaf) ($chunkKB KB)" -ForegroundColor Gray
}

Write-Host "[OK] $chunks trozo(s) generado(s) en $OutputDir" -ForegroundColor Green

# ── Instrucciones de reconstruccion ───────────────────────────────────────────
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host " Para reconstruir el bundle en el entorno destino (PowerShell):"   -ForegroundColor White
Write-Host " NOTA: es un bundle 'thin' — el destino debe tener ya la base '$Base'." -ForegroundColor Yellow
Write-Host ""
Write-Host "   # 1. Juntar todos los trozos en un unico .b64"
Write-Host "   Get-Content $SafeName.bundle.b64.* | Set-Content joined.b64 -Encoding ascii"
Write-Host ""
Write-Host "   # 2. Decodificar a bundle"
Write-Host "   `$b64 = Get-Content joined.b64 -Raw"
Write-Host "   [IO.File]::WriteAllBytes('$SafeName.bundle', [Convert]::FromBase64String(`$b64.Trim()))"
Write-Host ""
Write-Host "   # 3. Verificar e importar la rama"
Write-Host "   git bundle verify $SafeName.bundle"
Write-Host "   git fetch $SafeName.bundle '$Branch`:$Branch'"
Write-Host "   git checkout $Branch"
Write-Host ""
Write-Host "   # 4. Publicar la rama y abrir el PR"
Write-Host "   git push -u origin $Branch"
Write-Host "   gh pr create"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor DarkGray
Write-Host ""
