#!/bin/bash
set -e

echo "==================================="
echo "CESM Status Board - GitHub Pages Deploy"
echo "==================================="

# Check if we're on main branch
current_branch=$(git branch --show-current)
if [ "$current_branch" != "main" ]; then
    echo "Warning: Not on main branch (currently on: $current_branch)"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update data (optional - comment out if you want to deploy without updating)
echo ""
echo "Step 1: Updating data..."
python scripts/update_data.py --mode=incremental

# Export to JSON
echo ""
echo "Step 2: Exporting to JSON..."
python scripts/export_static.py --output=web/data/

# Check if gh-pages branch exists
if git show-ref --quiet refs/heads/gh-pages; then
    echo ""
    echo "Step 3: Deploying to existing gh-pages branch..."

    # Stash any changes
    git stash push -m "Pre-deploy stash"

    # Switch to gh-pages
    git checkout gh-pages

    # Copy updated data files
    cp -r web/data/*.json data/ 2>/dev/null || mkdir -p data && cp -r web/data/*.json data/

    # Commit changes
    git add data/
    git commit -m "Update data - $(date '+%Y-%m-%d %H:%M:%S')" || echo "No changes to commit"

    # Push to remote
    echo ""
    echo "Step 4: Pushing to GitHub..."
    git push origin gh-pages

    # Return to main branch
    git checkout main

    # Restore stashed changes if any
    git stash pop || true

else
    echo ""
    echo "Step 3: Creating gh-pages branch..."

    # Create orphan gh-pages branch
    git checkout --orphan gh-pages

    # Remove all files from staging
    git rm -rf .

    # Copy web files to root
    cp web/index.html .
    cp -r web/css .
    cp -r web/js .
    cp -r web/data .

    # Create README for gh-pages
    echo "# CESM Development Status Board" > README.md
    echo "" >> README.md
    echo "This is the GitHub Pages deployment of the CESM Development Status Board." >> README.md
    echo "" >> README.md
    echo "View the live site at: https://brianpm.github.io/cesm_dev_statboard/" >> README.md

    # Add and commit
    git add .
    git commit -m "Initial GitHub Pages deployment"

    # Push to remote
    echo ""
    echo "Step 4: Pushing to GitHub..."
    git push -u origin gh-pages

    # Return to main branch
    git checkout main
fi

echo ""
echo "==================================="
echo "Deployment Complete!"
echo "==================================="
echo ""
echo "Your site should be available at:"
echo "https://brianpm.github.io/cesm_dev_statboard/"
echo ""
echo "Note: It may take a few minutes for GitHub Pages to update."
echo "==================================="
