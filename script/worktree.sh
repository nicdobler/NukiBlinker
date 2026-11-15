#!/bin/bash
# Gestiona git worktrees para lanzar agentes en paralelo sobre NukiBlinker.
#
# Cada worktree es un directorio de trabajo independiente vinculado al mismo
# repositorio (.git), con su propia rama creada desde origin/main. Los agentes
# solo EDITAN y hacen PUSH; la validacion (lint + test) ocurre en CI.
#
# Usage:
#   ./script/worktree.sh new    feat/login
#   ./script/worktree.sh list
#   ./script/worktree.sh remove feat/login
#
# Variable opcional: WORKTREE_ROOT (por defecto <repo-parent>/NukiBlinker-wt)

set -e

ACTION="$1"
BRANCH="$2"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="${WORKTREE_ROOT:-$(dirname "$REPO_ROOT")/NukiBlinker-wt}"

slug() { echo "$1" | sed 's#[/\\]#-#g'; }

case "$ACTION" in
    new)
        [ -z "$BRANCH" ] && { echo "[ERR] Falta la rama (ej: new feat/login)."; exit 1; }
        SLUG="$(slug "$BRANCH")"
        PATH_WT="$ROOT/$SLUG"
        [ -e "$PATH_WT" ] && { echo "[ERR] Ya existe: $PATH_WT"; exit 1; }

        echo ""
        echo "[*] Fetching origin..."
        git -C "$REPO_ROOT" fetch origin
        mkdir -p "$ROOT"

        echo "[*] Creando worktree '$BRANCH' desde origin/main..."
        git -C "$REPO_ROOT" worktree add -b "$BRANCH" "$PATH_WT" origin/main

        echo ""
        echo "[OK] Worktree listo:"
        echo "     Rama : $BRANCH"
        echo "     Ruta : $PATH_WT"
        echo ""
        echo "     Al terminar: git -C \"$PATH_WT\" push -u origin $BRANCH"
        ;;
    list)
        echo ""
        echo "[i] Worktrees activos:"
        git -C "$REPO_ROOT" worktree list
        ;;
    remove)
        [ -z "$BRANCH" ] && { echo "[ERR] Falta la rama (ej: remove feat/login)."; exit 1; }
        SLUG="$(slug "$BRANCH")"
        PATH_WT="$ROOT/$SLUG"

        echo ""
        echo "[x] Eliminando worktree: $PATH_WT"
        git -C "$REPO_ROOT" worktree remove "$PATH_WT"
        git -C "$REPO_ROOT" worktree prune

        echo "[OK] Worktree eliminado. La rama '$BRANCH' sigue existiendo (borrala tras el merge)."
        ;;
    *)
        echo "Usage: $0 {new|list|remove} [branch]"
        exit 1
        ;;
esac
