#!/bin/bash
#
# Manual setup for dev-context git repository
# Alternative to using 'gh' CLI
#

set -e

echo "🚀 Setting up dev-context repository..."
echo ""

# Step 1: Run the automated setup
echo "📦 Step 1: Creating dev-context/ folder..."
if [ ! -f "./scripts/setup_dev_context.sh" ]; then
    echo "❌ Error: scripts/setup_dev_context.sh not found"
    echo "   Make sure you're in the rmirror-cloud directory"
    exit 1
fi

./scripts/setup_dev_context.sh

echo ""
echo "✅ dev-context/ created successfully!"
echo ""

# Step 2: Instructions for GitHub
echo "📝 Step 2: Create private GitHub repository"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1. Go to: https://github.com/new"
echo ""
echo "2. Fill in:"
echo "   Repository name: rmirror-dev-context"
echo "   Description: Private development context for rMirror Cloud"
echo "   ☑ Private"
echo "   ☐ Add README (we already have one)"
echo "   ☐ Add .gitignore (we already have one)"
echo ""
echo "3. Click 'Create repository'"
echo ""
echo "4. Copy the SSH URL (should look like):"
echo "   git@github.com:YOUR-USERNAME/rmirror-dev-context.git"
echo ""

# Wait for user
read -p "Press Enter when you've created the GitHub repo and copied the SSH URL..."

echo ""
echo "📤 Step 3: Enter your repository SSH URL"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -p "Paste the SSH URL here: " REPO_URL

if [ -z "$REPO_URL" ]; then
    echo "❌ Error: No URL provided"
    exit 1
fi

# Step 4: Connect and push
echo ""
echo "🔗 Step 4: Connecting to GitHub..."
cd dev-context

# Add remote
git remote add origin "$REPO_URL"
echo "✅ Added remote 'origin'"

# Push
echo ""
echo "📤 Pushing to GitHub..."
git push -u origin main

echo ""
echo "🎉 Success! dev-context repository is now on GitHub!"
echo ""
echo "📋 Summary:"
echo "   Local:  $(pwd)"
echo "   Remote: $REPO_URL"
echo "   Branch: main"
echo ""
echo "✅ Setup complete! You can now:"
echo "   1. Read dev-context/README.md for workflow documentation"
echo "   2. Start your first focused Claude Code session"
echo "   3. See DEV-SETUP.md in main repo for quick reference"
echo ""

