"""Dessine l'icône de l'app (fond noir, « € » blanc) et produit un .icns.

    uv run python dev/icone.py build/Compta pro.icns
"""
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TAILLE = 1024
POLICE = "/System/Library/Fonts/SFNS.ttf"  # police système (San Francisco)


def dessiner() -> Image.Image:
    img = Image.new("RGBA", (TAILLE, TAILLE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    marge = 100  # grille des icônes macOS : carré arrondi de 824 px dans 1024
    d.rounded_rectangle((marge, marge, TAILLE - marge, TAILLE - marge), radius=185, fill=(0, 0, 0, 255))
    police = ImageFont.truetype(POLICE, 560)
    try:
        police.set_variation_by_name("Bold")
    except (OSError, ValueError):
        pass
    x0, y0, x1, y1 = d.textbbox((0, 0), "€", font=police)
    d.text(((TAILLE - (x1 - x0)) / 2 - x0, (TAILLE - (y1 - y0)) / 2 - y0), "€", font=police, fill="white")
    return img


def main(sortie: Path) -> None:
    img = dessiner()
    with tempfile.TemporaryDirectory() as tmp:
        jeu = Path(tmp) / "icone.iconset"
        jeu.mkdir()
        for base in (16, 32, 128, 256, 512):
            for echelle in (1, 2):
                px = base * echelle
                nom = f"icon_{base}x{base}{'@2x' if echelle == 2 else ''}.png"
                img.resize((px, px), Image.LANCZOS).save(jeu / nom)
        sortie.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["iconutil", "-c", "icns", str(jeu), "-o", str(sortie)], check=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
