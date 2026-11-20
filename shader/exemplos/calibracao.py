#!/usr/bin/env python3
"""Tela de calibracao usada como entrada dos exemplos: barras de cor, rampa de cinza, grade, circulo e dois objetos em movimento.

  python calibracao.py saida.png            # quadro parado
  from calibracao import quadro             # quadro(W, H, t) -> RGBA uint8 (H, W, 4)
"""
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BARRAS = [(235, 235, 235), (235, 235, 16), (16, 235, 235), (16, 235, 16), (235, 16, 235), (235, 16, 16), (16, 16, 235)]
INVERTIDAS = [(16, 16, 235), (16, 16, 16), (235, 16, 235), (16, 16, 16), (16, 235, 235), (16, 16, 16), (235, 235, 235)]
_cache = {}


def _fonte(tam):
    for nome in ('arial.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(nome, tam)
        except OSError:
            pass
    return ImageFont.load_default()


def base(W, H):
    if (W, H) in _cache:
        return _cache[(W, H)]
    im = Image.new('RGB', (W, H), (24, 24, 24))
    d = ImageDraw.Draw(im)
    hb, hr, bw = int(H * .40), int(H * .06), W / 7
    for i, c in enumerate(BARRAS):
        d.rectangle([round(i * bw), 0, round((i + 1) * bw) - 1, hb - 1], fill=c)
    for i, c in enumerate(INVERTIDAS):   # faixa de cores invertidas
        d.rectangle([round(i * bw), hb, round((i + 1) * bw) - 1, hb + hr - 1], fill=c)
    y1 = hb + hr
    for i in range(16):   # rampa de cinza em 16 degraus
        g = round(i * 255 / 15)
        d.rectangle([round(i * W / 16), y1, round((i + 1) * W / 16) - 1, y1 + hr - 1], fill=(g, g, g))
    ya = y1 + hr
    for x in range(0, W, 32):   # grade
        d.line([x, ya, x, H], fill=(70, 70, 70))
    for y in range(ya, H, 32):
        d.line([0, y, W, y], fill=(70, 70, 70))
    cy, r = (ya + H) // 2, min((H - ya) // 2 - 3, 48)
    d.ellipse([W // 2 - r, cy - r, W // 2 + r, cy + r], outline=(235, 235, 235), width=2)
    d.line([W // 2 - r, cy, W // 2 + r, cy], fill=(235, 235, 235))
    d.line([W // 2, cy - r, W // 2, cy + r], fill=(235, 235, 235))
    for x in range(-H, W, 24):   # diagonais finas: bordas que mostram o jitter
        d.line([x, H, x + (H - ya), ya], fill=(55, 55, 55))
    d.text((8, ya + 4), 'RETROit  %dx%d' % (W, H), fill=(235, 235, 235), font=_fonte(max(12, H // 12)))
    d.text((8, ya + 4 + H // 10), 'ABCDEFGHIJKLM 0123456789', fill=(235, 235, 235), font=_fonte(max(10, H // 16)))
    _cache[(W, H)] = np.asarray(im.convert('RGBA'))
    return _cache[(W, H)]


def quadro(W, H, t=0.0):
    f = base(W, H).copy()
    ya = int(H * .40) + 2 * int(H * .06)
    lado = max(8, H // 12)
    alt = H - ya
    x = int((.5 + .5 * np.sin(t * 1.6)) * (W - lado - 8)) + 4   # quadrado branco indo e voltando
    y = ya + (alt - lado) // 2 - 12
    f[y:y + lado, x:x + lado] = (235, 235, 235, 255)
    im = Image.fromarray(f)
    d = ImageDraw.Draw(im)   # bola vermelha em arco
    bx = int((t * 70) % (W + 40)) - 20
    by = ya + int(abs(np.sin(t * 2.4)) * (alt - lado))
    d.ellipse([bx - lado // 2, by, bx + lado // 2, by + lado], fill=(235, 40, 40, 255))
    return np.asarray(im)


if __name__ == '__main__':
    Image.fromarray(quadro(640, 360, 1.0)).convert('RGB').save(sys.argv[1] if len(sys.argv) > 1 else 'calibracao.png')
