#!/bin/bash
# Lance Compta pro depuis les sources sur une base d'essai locale (dev/essai/, ignorée par git),
# sans toucher aux vraies données. Déposer des exports Ingenus dans « dev/essai/exports Ingenus/ ».
cd "$(dirname "$0")/.." || exit 1
mkdir -p "dev/essai/exports Ingenus"
uv run -q python outil/compta.py --donnees dev/essai "$@"
