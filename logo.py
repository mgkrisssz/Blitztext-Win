"""
Blitztext-Logo: weisser Blitz auf abgerundetem Quadrat. Wird fuer das Tray-Icon
(Hintergrundfarbe = Status) und fuer das Repo-Logo (docs/logo.png) benutzt.

Neu erzeugen:  python logo.py   (schreibt docs/logo.png)
"""

import os
from PIL import Image, ImageDraw

TERRAKOTTA = (201, 100, 66, 255)

# Blitz in einem 64x64-Raster
_BLITZ = [(38, 4), (13, 35), (28, 35), (22, 60), (51, 25), (35, 25), (45, 4)]


def blitz_icon(hintergrund=TERRAKOTTA, groesse=64):
    """Quadratisches Icon mit abgerundeten Ecken und weissem Blitz (weich gezeichnet)."""
    f = 8                                    # 8-fach grosser zeichnen, dann verkleinern
    g = groesse * f
    img = Image.new("RGBA", (g, g), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, g - 1, g - 1), radius=int(g * 0.22), fill=hintergrund)
    k = g / 64.0
    d.polygon([(x * k, y * k) for x, y in _BLITZ], fill=(255, 255, 255, 255))
    return img.resize((groesse, groesse), Image.LANCZOS)


if __name__ == "__main__":
    ziel = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "logo.png")
    blitz_icon(groesse=256).save(ziel)
    print("geschrieben:", ziel)
