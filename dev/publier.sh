#!/bin/bash
# Publie une version : construit l'app, crée le tag git vX.Y.Z et la release GitHub
# avec le .dmg (1re installation) et le .zip (mise à jour automatique dans l'app).
#   dev/publier.sh 1.0.1 "Ce qui change (affiché à la titulaire dans la fenêtre de mise à jour)"
set -euo pipefail
cd "$(dirname "$0")/.."
V="${1:?Usage : dev/publier.sh X.Y.Z \"ce qui change\"}"
NOTES="${2:-Version $V}"
[[ "$V" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "❌ Version attendue sous la forme X.Y.Z"; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "❌ Des modifications ne sont pas commitées."; git status --short; exit 1; }
git rev-parse "v$V" >/dev/null 2>&1 && { echo "❌ La version $V existe déjà."; exit 1; }
DERNIERE=$(git tag -l 'v*' --sort=-v:refname | head -1 | sed 's/^v//')
if [ -n "$DERNIERE" ] && [ "$(printf '%s\n%s\n' "$DERNIERE" "$V" | sort -V | tail -1)" != "$V" ]; then
  echo "❌ $V n'est pas plus récente que la dernière version ($DERNIERE)."; exit 1
fi
dev/construire.sh "$V"
git tag "v$V" && git push -q origin HEAD "v$V"
gh release create "v$V" "dist/Compta-pro-$V.dmg" "dist/Compta-pro-$V.zip" --title "Compta pro $V" --notes "$NOTES"
echo "✅ Publiée : $(gh release view "v$V" --json url -q .url)"
