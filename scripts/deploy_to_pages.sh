#!/bin/bash
#
# deploy_to_pages.sh - Deploy CESM Status Board to GitHub Pages
#
# Uses git worktree to update the gh-pages branch without ever switching the
# main working directory away from the main branch.  This avoids the hazard
# where branch-switching overwrites or clears gitignored files such as
# data/cesm_dev.db (which is tracked on gh-pages but gitignored on main).
#
# Usage:
#   bash scripts/deploy_to_pages.sh [--skip-collect] [--full]
#
#   --skip-collect   Skip data collection; re-export from the existing database
#   --full           Run a full collection (default: incremental)
#
set -euo pipefail

PYTHON=${PYTHON:-/glade/u/apps/opt/conda/envs/npl/bin/python}
WORKTREE_DIR=/tmp/cesm_dev_ghpages_worktree
STAGING_DIR=/tmp/cesm_dev_deploy_staging

SKIP_COLLECT=false
COLLECT_MODE=incremental

for arg in "$@"; do
    case "$arg" in
        --skip-collect) SKIP_COLLECT=true ;;
        --full)         COLLECT_MODE=full ;;
    esac
done

echo "==================================="
echo "CESM Status Board - GitHub Pages Deploy"
echo "==================================="
echo ""
echo "Python:       $PYTHON"
echo "Collect mode: $COLLECT_MODE (skip=$SKIP_COLLECT)"
echo ""

# ── Verify we are on main ───────────────────────────────────────────────────
current_branch=$(git branch --show-current)
if [ "$current_branch" != "main" ]; then
    echo "Warning: Not on main branch (currently on: $current_branch)"
    read -rp "Continue anyway? (y/n) " reply
    [[ $reply =~ ^[Yy]$ ]] || exit 1
fi

# ── Step 1: Data collection ──────────────────────────────────────────────────
if [ "$SKIP_COLLECT" = false ]; then
    echo "Step 1: Collecting data (mode=$COLLECT_MODE)..."
    if [ "$COLLECT_MODE" = "full" ]; then
        $PYTHON scripts/collect_data.py --mode=full
    else
        $PYTHON scripts/update_data.py --mode=incremental
    fi
else
    echo "Step 1: Skipping data collection (--skip-collect)"
fi

# ── Step 2: Export to JSON ───────────────────────────────────────────────────
echo ""
echo "Step 2: Exporting database to JSON..."
mkdir -p "$STAGING_DIR"
$PYTHON scripts/export_static.py --output="$STAGING_DIR/"
echo "  Exported to $STAGING_DIR/"
ls -lh "$STAGING_DIR/"

# ── Step 3: Set up gh-pages worktree ────────────────────────────────────────
echo ""
echo "Step 3: Setting up gh-pages worktree..."

# Clean up any leftover worktree from a previous failed run
if [ -d "$WORKTREE_DIR" ]; then
    git worktree remove --force "$WORKTREE_DIR" 2>/dev/null || rm -rf "$WORKTREE_DIR"
fi

if git show-ref --quiet refs/heads/gh-pages; then
    git worktree add "$WORKTREE_DIR" gh-pages
else
    echo "ERROR: gh-pages branch does not exist."
    echo "Create it first with: git checkout --orphan gh-pages && git rm -rf ."
    exit 1
fi

# ── Step 4: Copy files into worktree ────────────────────────────────────────
echo ""
echo "Step 4: Updating files in gh-pages worktree..."

# Web application files (HTML/CSS/JS) from main branch working directory
cp    web/index.html        "$WORKTREE_DIR/index.html"
cp -r web/css/.             "$WORKTREE_DIR/css/"
cp -r web/js/.              "$WORKTREE_DIR/js/"

# Fresh JSON data files
mkdir -p "$WORKTREE_DIR/data"
cp "$STAGING_DIR/"*.json    "$WORKTREE_DIR/data/"
if [ -d "$STAGING_DIR/namelists" ]; then
    cp -r "$STAGING_DIR/namelists" "$WORKTREE_DIR/data/"
fi

# ── Step 5: Commit and push ──────────────────────────────────────────────────
echo ""
echo "Step 5: Committing and pushing gh-pages..."

n_cases=$(python3 -c "import json; d=json.load(open('$STAGING_DIR/last_update.json')); print(d['total_cases'])" 2>/dev/null || echo "?")
n_diag=$(python3  -c "import json; d=json.load(open('$STAGING_DIR/last_update.json')); print(d['cases_with_diagnostics'])" 2>/dev/null || echo "?")
commit_msg="Update site - ${n_cases} cases, ${n_diag} with diagnostics ($(date '+%Y-%m-%d'))"

git -C "$WORKTREE_DIR" add data/ css/ js/ index.html
git -C "$WORKTREE_DIR" commit -m "$commit_msg" || echo "  No changes to commit"
git -C "$WORKTREE_DIR" push origin gh-pages

# ── Step 6: Clean up ────────────────────────────────────────────────────────
git worktree remove "$WORKTREE_DIR"
rm -rf "$STAGING_DIR"

echo ""
echo "==================================="
echo "Deployment Complete!"
echo "==================================="
echo ""
echo "Site: https://brianpm.github.io/cesm_dev_statboard/"
echo "Note: GitHub Pages may take a few minutes to update."
echo "==================================="
