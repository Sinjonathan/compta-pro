#!/bin/bash
# Construit dist/Compta pro.app, dist/Compta-pro-<VERSION>.dmg (1re installation)
# et dist/Compta-pro-<VERSION>.zip (mise à jour automatique), pour Mac Apple Silicon.
#   dev/construire.sh 1.2.0     (par défaut : « dev »)
set -euo pipefail
cd "$(dirname "$0")/.."
RACINE="$PWD"
V="${1:-dev}"
uv sync -q --frozen                                         # environnement conforme à uv.lock
echo "VERSION = \"$V\"" > outil/_version.py
trap 'rm -f outil/_version.py' EXIT
rm -rf build dist
uv run -q python dev/icone.py "build/Compta pro.icns"
uv run -q pyinstaller --noconfirm --clean --windowed --log-level WARN \
  --name "Compta pro" --osx-bundle-identifier "io.github.compta-pro" --icon "$RACINE/build/Compta pro.icns" \
  --paths "$RACINE/outil" --hidden-import _version --exclude-module PIL --exclude-module tkinter --strip \
  --add-data "$RACINE/outil/ui:ui" --add-data "$RACINE/outil/defaut:defaut" \
  --distpath dist --workpath build/pyi --specpath build \
  outil/app.py
APP="dist/Compta pro.app"
PL="$APP/Contents/Info.plist"
plutil -replace LSUIElement -bool true "$PL"               # icône dans la barre des menus, pas de Dock
plutil -replace CFBundleShortVersionString -string "$V" "$PL"
plutil -replace CFBundleVersion -string "$V" "$PL"
codesign --force --deep --sign - "$APP"                     # signature locale (pas de compte Apple)
ditto -c -k --keepParent "$APP" "dist/Compta-pro-$V.zip"
mkdir -p build/dmg && cp -R "$APP" build/dmg/ && ln -sf /Applications build/dmg/Applications
hdiutil create -quiet -volname "Compta pro $V" -srcfolder build/dmg -ov -format UDZO "dist/Compta-pro-$V.dmg"
rm -rf "dist/Compta pro"
echo "✅ Version $V :"
ls -lh dist | grep -v total
