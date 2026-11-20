#!/usr/bin/env python3
"""Objeto low poly girando (icosaedro, sombreado chapado) como quadro-base: so numpy e PIL, sem Blender.

  from lowpoly import quadro   # quadro(W, H, t) -> RGBA uint8 (H, W, 4)
"""
import numpy as np
from PIL import Image, ImageDraw

_p = (1 + 5 ** .5) / 2
V = np.array([(-1, _p, 0), (1, _p, 0), (-1, -_p, 0), (1, -_p, 0), (0, -1, _p), (0, 1, _p), (0, -1, -_p), (0, 1, -_p),
              (_p, 0, -1), (_p, 0, 1), (-_p, 0, -1), (-_p, 0, 1)], float)
V /= np.linalg.norm(V[0])
F = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
     (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
COR = np.array([(200, 90, 60), (70, 150, 210), (230, 200, 80), (90, 190, 110)], float)


UV = [(14, 114), (114, 114), (64, 14)]   # triangulo da textura onde cada face e mapeada
_tex = {}


def textura(k):
    """Textura 128x128 da face: xadrez de 16 px na cor da face, listras e uma letra, para o jitter ter o que deformar."""
    if k in _tex: return _tex[k]
    c = tuple(int(v) for v in COR[k]); es = tuple(int(v * .45) for v in COR[k])
    im = Image.new('RGB', (128, 128), c); d = ImageDraw.Draw(im)
    for y in range(0, 128, 32):
        for x in range(0, 128, 32):
            if (x // 32 + y // 32) % 2: d.rectangle([x, y, x + 31, y + 31], fill=es)
    for x in range(-128, 128, 64): d.line([x, 128, x + 128, 0], fill=(235, 235, 235), width=2)
    d.text((54, 52), 'ABCD'[k], fill=(255, 255, 255))
    _tex[k] = im; return im


def _rot(a, b):
    ca, sa, cb, sb = np.cos(a), np.sin(a), np.cos(b), np.sin(b)
    return np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]]) @ np.array([[1, 0, 0], [0, cb, -sb], [0, sb, cb]])


def quadro(W, H, t=0.0):
    im = Image.new('RGBA', (W, H), (24, 24, 28, 255)); d = ImageDraw.Draw(im)
    K = max(1., H / 540); G = int(32 * K)
    for x in range(0, W, G): d.line([x, 0, x, H], fill=(70, 70, 76))   # grade parada ao fundo: mostra que so o objeto em movimento treme
    for y in range(0, H, G): d.line([0, y, W, y], fill=(70, 70, 76))
    R = _rot(t * .4, .5 + .3 * np.sin(t * .7)); P = V @ R.T * (min(W, H) * .50)
    P[:, 2] += 2.6 * min(W, H); s = 2.1 * min(W, H) / P[:, 2:3]   # perspectiva simples
    xy = P[:, :2] * s + (W / 2, H / 2)
    luz = np.array([.4, -.6, -.7]); luz /= np.linalg.norm(luz)
    fs = []
    for i, f in enumerate(F):
        a, b, c = P[list(f)]; n = np.cross(b - a, c - a); n /= np.linalg.norm(n)
        if n @ (a + b + c) / 3 >= 0: continue   # face de costas
        fs.append(((a[2] + b[2] + c[2]) / 3, i, .55 + .45 * max(0., -(n @ luz))))
    for _, i, l in sorted(fs, reverse=True):
        tri = [tuple(xy[j]) for j in F[i]]
        A = np.array([[x, y, 1] for x, y in tri]); M = np.linalg.solve(A, np.array(UV, float))   # tela -> textura (afim, como no PS1)
        tx = textura(i % 4).transform((W, H), Image.AFFINE, (M[0, 0], M[1, 0], M[2, 0], M[0, 1], M[1, 1], M[2, 1]), Image.NEAREST)
        tx = Image.eval(tx, lambda v: int(v * l))
        m = Image.new('L', (W, H), 0); ImageDraw.Draw(m).polygon(tri, fill=255)
        im.paste(tx.convert('RGBA'), (0, 0), m)
        d = ImageDraw.Draw(im); d.polygon(tri, outline=(235, 235, 235, 255), width=max(2, int(2 * K)))
    return np.asarray(im)


if __name__ == '__main__':
    import sys
    Image.fromarray(quadro(640, 360, 1.0)).convert('RGB').save(sys.argv[1] if len(sys.argv) > 1 else 'lowpoly.png')
