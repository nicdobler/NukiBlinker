<#
.SYNOPSIS
    Gestiona git worktrees para lanzar agentes en paralelo sobre NukiBlinker.
.DESCRIPTION
    Cada worktree es un directorio de trabajo independiente vinculado al mismo
    repositorio (.git), con su propia rama creada desde origin/main. Permite que
    varios agentes editen en carpetas separadas sin pisarse el arbol de trabajo.

    Los agentes solo EDITAN y hacen PUSH: la validacion (lint + test) ocurre en CI.
    No se crea .venv ni se instalan dependencias localmente.
.PARAMETER Action
    new    -> crea un worktree + rama nueva desde origin/main
    list   -> lista los worktrees existentes
    remove -> elimina el worktree de una rama y hace prune
.PARAMETER Branch
    Nombre de la rama (ej: feat/login). Requerido para new y remove.
.PARAMETER Root
    Carpeta raiz donde viven los worktrees. Por defecto, hermana del repo:
    <repo-parent>\NukiBlinker-wt
.EXAMPLE
    .\script\worktree.ps1 -Action new    -Branch feat/login
    .\script\worktree.ps1 -Action list
    .\script\worktree.ps1 -Action remove -Branch feat/login
#>

param(
    [Parameter(Mandatory)][ValidateSet('new', 'list', 'remove')][string]$Action,
    [string]$Branch,
    [string]$Root
)

$ErrorActionPreference = 'Stop'

# Raiz del repo = carpeta superior de la ubicacion de este script (script\..)
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

if (-not $Root) {
    $Root = Join-Path (Split-Path $RepoRoot -Parent) 'NukiBlinker-wt'
}

function Get-Slug([string]$name) {
    return ($name -replace '[/\\]', '-')
}

switch ($Action) {
    'new' {
        if (-not $Branch) { throw 'Falta -Branch (ej: -Branch feat/login).' }
        $slug = Get-Slug $Branch
        $path = Join-Path $Root $slug

        if (Test-Path $path) { throw "Ya existe la carpeta: $path" }

        Write-Host ""
        Write-Host "[*] Fetching origin..." -ForegroundColor Cyan
        git -C $RepoRoot fetch origin

        if (-not (Test-Path $Root)) {
            New-Item -ItemType Directory -Path $Root | Out-Null
        }

        Write-Host "[*] Creando worktree '$Branch' desde origin/main..." -ForegroundColor Cyan
        git -C $RepoRoot worktree add -b $Branch $path origin/main

        Write-Host ""
        Write-Host "[OK] Worktree listo:" -ForegroundColor Green
        Write-Host "     Rama : $Branch" -ForegroundColor Gray
        Write-Host "     Ruta : $path" -ForegroundColor Gray
        Write-Host ""
        Write-Host "     El agente debe trabajar dentro de esa carpeta y al terminar:" -ForegroundColor Gray
        Write-Host "       git -C `"$path`" push -u origin $Branch" -ForegroundColor DarkGray
    }
    'list' {
        Write-Host ""
        Write-Host "[i] Worktrees activos:" -ForegroundColor Yellow
        git -C $RepoRoot worktree list
    }
    'remove' {
        if (-not $Branch) { throw 'Falta -Branch (ej: -Branch feat/login).' }
        $slug = Get-Slug $Branch
        $path = Join-Path $Root $slug

        Write-Host ""
        Write-Host "[x] Eliminando worktree: $path" -ForegroundColor Cyan
        git -C $RepoRoot worktree remove $path
        git -C $RepoRoot worktree prune

        Write-Host "[OK] Worktree eliminado. La rama '$Branch' sigue existiendo (borrala tras el merge)." -ForegroundColor Green
    }
}
