
# .github/workflows/update-feed.yml
name: Update CourtListener Feed

on:
  workflow_dispatch: {}
  schedule:
    # Every day at 07:15 and 13:15 UTC (works for London office hours; tweak as needed)
    - cron: "15 7 * * *"
    - cron: "15 13 * * *"

permissions:
  contents: write   # required to push changes

jobs:
  build-and-publish:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          python -m pip install requests

      - name: Build Atom feed
        env:
          DOCKET_ID: "68024915"
          DOCKET_SLUG: "alter-v-openai-inc"
          # Replace with your actual Pages URL:
          FEED_SELF_URL: "https://michaellee50.github.io/CourtListener/feed.xml"
        run: |
          python scripts/build_feed.py

      - name: Commit if changed
        run: |
          if [[ -n "$(git status --porcelain)" ]]; then
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add feed.xml
            git commit -m "Auto-update feed.xml from CourtListener ${DOCKET_ID}"
            git push
          else
            echo "No changes to commit."
          fi
