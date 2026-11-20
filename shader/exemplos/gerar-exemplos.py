#!/usr/bin/env python3
"""Gera os videos de exemplo (5 s, 640x360, 30 fps) com a tela de calibracao como entrada.

  python shader/exemplos/gerar-exemplos.py [nome ...]      # sem nome, gera todos; saida em shader/exemplos/saidas

Exemplos: ps1-jitter, aviso-guerra-fria, print-repassado, varredura-linhas, crt-fosforo.
Cada um e um preset do RETROit (dicionario abaixo, mesmas chaves do JSON do app) mais o que muda no tempo.
"""
import importlib.util, os, sys
from fractions import Fraction
import numpy as np, av
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
SAIDAS = os.path.join(HERE, 'saidas')
sp = importlib.util.spec_from_file_location('rv', os.path.join(HERE, '..', 'retroit-video.py'))
rv = importlib.util.module_from_spec(sp); sp.loader.exec_module(rv)
sys.path.insert(0, HERE)
from calibracao import quadro
import lowpoly

FPS, SEG = 30, 5
LADOS = ('ps1-jitter', 'crt-fosforo-lado', 'jitter-blocos')   # demos lado a lado (antes e depois) sobre o objeto low poly


def fonte(tam):
    for n in ('arialbd.ttf', 'arial.ttf', 'DejaVuSans-Bold.ttf'):
        try: return ImageFont.truetype(n, tam)
        except OSError: pass
    return ImageFont.load_default()

# base PS1 (pixel 3, 15 bits com dither Bayer) e jitter leve e lento, sem guia de movimento
PS1_JITTER = dict(pixel=3, bits=5, dither='bayer4', ditherAmt=1, gamma=.9, lift=.03, sat=1.05, contrast=1.05, scan=.06, vig=.25,
                  jtOn=1, jtAmt=2, jtBlock=8, jtDensity=.3, jtHold=6, jtMove=0, uRatio=2)   # uRatio 2: pixelizacao e blocos na escala de 1080 de altura
# preset definitivo do Reel + o tremor vertical que o Remotion fazia no aviso (2 px a cada 2 quadros)
AVISO = dict(ntOn=1, dsOn=1, tpOn=1, jpOn=1, off=['color', 'crt', 'halftone', 'noise', 'palette', 'pixel', 'scan', 'vig'],
             pixel=1, bits=8, dither='none', ditherAmt=0, ntChroma=0, ntDelay=0, ntRing=0, ntSmear=0, ntVary=1, ntRs=1, ntGrain=6, uRatio=1,
             ntHold=2, ntNoise=.04, ntFieldNoise=.0875, ntCNoise=.05, ntPhase=.29, ntNest=.5, ntWave=0,
             dsJitter=1, dsWaveX=4, dsWaveFreq=3, dsEdge=1, dsShake=2, dsShakeHold=2,
             dsLineRep=6, dsLineCount=1, dsLineH=1, dsLineDev=2, dsLineDevRows=3,
             tpShift=2, tpSmear=16, tpGhost=.5, tpRing=1, tpStreak=1, jpQ=15, jpPass=3, jpSub=3, jpSharp=.1)
# so a copia de copia: fita magnetica e depois JPEG pesado (nada de cor, NTSC ou distorcao)
PRINT = dict(tpOn=1, tpShift=5, tpSmear=7, tpGhost=.16, tpRing=.35, tpStreak=.5, jpOn=1, jpVary=1, jpQ=22, jpPass=3, jpSub=2, jpSharp=.6, ntHold=2,
             off=['color', 'pixel', 'palette', 'ntsc', 'distort', 'halftone', 'scan', 'vig', 'noise', 'crt', 'jitter'])
# so as linhas repetidas em varredura (sem NTSC, jitter ou onda); a posicao dsLinePos vai de 0 a 1 em 5 s
VARREDURA = dict(dsOn=1, dsEdge=1, dsLineRep=10, dsLineCount=1, dsLineH=1, dsLineDev=6, dsLineDevRows=3,
                 off=['color', 'pixel', 'palette', 'ntsc', 'halftone', 'scan', 'vig', 'noise', 'crt', 'jitter', 'tape', 'jpeg'])
# so o CRT: chuvisco NTSC por baixo, mascara de fosforo em celulas arredondadas, bloom e curvatura do tubo (dsBarrel; sem pixel, paleta, scanlines, jitter ou vinheta)
CRT = dict(pixel=1, bits=8, dither='none', crt=1, crtMask=.65, crtBloom=.35, crtCorner=.12, crtMaskY=1, crtMaskYInt=.5, crtMaskR=3, crtStagger=1,
           dsOn=1, dsBarrel=.02, dsZoom=1.02, order=['pixel', 'jitter', 'jpeg', 'ntsc', 'crt', 'distort'], jtOn=1, jtAmt=1, jtBlock=8, jtDensity=.3, jtHold=1, jtMove=0, jpOn=1, jpVary=1, jpQ=15, jpPass=1, jpSub=3, jpSharp=0,   # fosforo antes da curvatura: a mascara acompanha a curva
           ntOn=1, ntChroma=0, ntDelay=0, ntSmear=0, ntRing=0, ntWave=0, ntNoise=.112, ntFieldNoise=.0875, ntCNoise=.105, ntGrain=3, ntGrainV=3, ntRs=1, uRatio=1, ntVary=1, ntHold=2,
           off=['color', 'palette', 'halftone', 'scan', 'vig', 'noise', 'tape'])
# so o jitter de vertice, sem pixel, paleta nem outro efeito: blocos quadrados de 16 px deslocados, sorteio novo a cada 6 quadros
BLOCOS = dict(jtOn=1, jtAmt=3, jtBlock=16, jtDensity=.3, jtHold=6, jtMove=0, uRatio=2,
              off=['color', 'pixel', 'palette', 'ntsc', 'distort', 'halftone', 'scan', 'vig', 'noise', 'crt', 'tape', 'jpeg'])
def tempo_aviso(q, t, n):
    h = int(t * 15)
    q['dsPhase'] = (h / 15 * .6) % 1; q['dsWavePhase'] = (h / 15 * .15) % 1; q['dsLinePos'] = (t / SEG) % 1.0


def tempo_varredura(q, t, n):
    q['dsPhase'] = (int(t * 15) / 15 * .6) % 1; q['dsLinePos'] = (t / SEG) % 1.0   # a fase so sorteia o lado do desvio


EXEMPLOS = {'ps1-jitter': (PS1_JITTER, None), 'aviso-guerra-fria': (AVISO, tempo_aviso), 'print-repassado': (PRINT, None),
            'varredura-linhas': (VARREDURA, tempo_varredura), 'crt-fosforo': (CRT, None), 'crt-fosforo-lado': (CRT, None), 'jitter-blocos': (BLOCOS, None)}


TAMANHO = {'ps1-jitter': (1920, 1080), 'crt-fosforo-lado': (1920, 1080), 'jitter-blocos': (1920, 1080), 'aviso-guerra-fria': (1080, 608), 'print-repassado': (1080, 608), 'crt-fosforo': (1920, 1080)}   # largura do Reel: os px da fita e do JPEG nao escalam, entao so valem nessa largura


def gerar(nome):
    preset, tempo = EXEMPLOS[nome]
    W, H = TAMANHO.get(nome, (640, 360))
    P = rv.fresh(dict(preset)); r = rv.Renderer(W, H)
    os.makedirs(SAIDAS, exist_ok=True)
    out = av.open(os.path.join(SAIDAS, nome + '.mp4'), 'w'); rate = Fraction(FPS)
    v = out.add_stream('libx264', rate=rate); LADO = nome in LADOS   # lado a lado: original a esquerda, com efeito a direita
    v.width, v.height, v.pix_fmt, v.options = W, H, 'yuv420p', {'crf': '24', 'preset': 'slow'}
    for n in range(FPS * SEG):
        t = n / FPS; q = dict(P)
        if tempo: tempo(q, t, n)
        qd = quadro(W, H, t)
        if nome in LADOS: qd = lowpoly.quadro(W, H, t)   # objeto low poly girando: movimento em todas as direcoes para o jitter guiado
        d = np.frombuffer(r.frame(qd.tobytes(), n, q), np.uint8).reshape(H, W, 4)
        if LADO:
            c0 = W // 4; mw = W // 2   # os dois renders em 1920x1080 sao cortados no centro (960x1080) e montados lado a lado
            d = np.concatenate([qd[:, c0:c0 + mw], d[:, c0:c0 + mw]], axis=1); im = Image.fromarray(d, 'RGBA'); dr = ImageDraw.Draw(im); ft = fonte(H // 14)   # legendas por cima, depois do efeito
            for x0, txt in ((0, 'ANTES'), (mw, 'DEPOIS')):
                bb = dr.textbbox((0, 0), txt, font=ft); tx, ty = x0 + (mw - (bb[2] - bb[0])) // 2, H - (bb[3] - bb[1]) - H // 20
                dr.rectangle([tx - 16, ty - 8, tx + bb[2] - bb[0] + 16, ty + bb[3] - bb[1] + 14], fill=(0, 0, 0, 170)); dr.text((tx, ty), txt, font=ft, fill=(255, 255, 255, 255))
            d = np.asarray(im).copy()
        if n == FPS * 2: Image.fromarray(d, 'RGBA').convert('RGB').save(os.path.join(SAIDAS, nome + '.png'))
        vf = av.VideoFrame.from_ndarray(np.ascontiguousarray(d), format='rgba'); vf.pts, vf.time_base = n, 1 / rate
        for op in v.encode(vf): out.mux(op)
    for op in v.encode(): out.mux(op)
    out.close(); print('ok', nome)


if __name__ == '__main__':
    for nome in (sys.argv[1:] or EXEMPLOS): gerar(nome)
