#!/usr/bin/env python3
"""Faixa de chuvisco NTSC varrendo a tela (imita a faixa suave do scanlines.gdshader do Mansao 468,
mas com o chuvisco NTSC do RETROit em vez de luz).

  imagem: python faixa-chuvisco.py quadro.png saida.png --t 3.0
  video:  python faixa-chuvisco.py video.mp4 saida.mp4

A faixa desce de cima para baixo (periodo 6,667 s, largura gaussiana de 1,44% da altura, como o `sweep` do
scanlines.gdshader). Dentro dela o quadro vem do RETROit com so o efeito NTSC ligado; fora, o quadro original.
"""
import argparse, colorsys, importlib.util, math, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('retroit_video', os.path.join(HERE, '..', 'retroit-video.py'))
rv = importlib.util.module_from_spec(spec); spec.loader.exec_module(rv)

# so o NTSC (chuvisco), sem pixelar nem reduzir cor; ruido muda a cada quadro (ntVary)
PRESET = dict(ntOn=1, pixel=1, down='nearest', bits=8, dither='none', ditherAmt=0, ntRs=1, ntVary=1,
              ntNoise=0.16, ntGrain=4, ntCNoise=0.03, ntSnow=0.01, ntFieldNoise=0.175, ntPhase=0.29, ntBurst=0.03,
              ntChroma=6, ntDelay=2, ntSmear=1, ntRing=0.3, ntWave=0,
              off=['palette', 'distort', 'tape', 'jpeg', 'halftone', 'scan', 'vig', 'noise', 'crt', 'color'])

def mascara(t, H, period, width, strength):
    y = (np.arange(H) + 0.5) / H
    pos = (t / period) % 1.0
    d = (y - pos) / width
    return (np.exp(-d * d) * strength).astype(np.float32)[:, None, None]

def ruido(r, p, rgba, n, a):
    """Chuvisco com graos `zoom` vezes maiores: o NTSC roda numa copia reduzida (graos de 4 px) e volta ampliada, sem suavizar."""
    from PIL import Image
    z = a.zoom
    H, W = rgba.shape[:2]
    sw, sh = max(2, W // z), max(2, H // z)
    small = np.asarray(Image.fromarray(rgba, 'RGBA').resize((sw, sh), Image.BOX), np.uint8)
    ns = np.frombuffer(r.frame(small.tobytes(), n, p), np.uint8).reshape(sh, sw, 4)
    big = np.repeat(np.repeat(ns, z, axis=0), z, axis=1)
    out = np.zeros(rgba.shape, np.uint8)
    h2, w2 = min(H, big.shape[0]), min(W, big.shape[1])
    out[:h2, :w2] = big[:h2, :w2]
    out[h2:, :] = out[h2 - 1:h2, :]; out[:, w2:] = out[:, w2 - 1:w2]
    return out

def picotes(W, H, t, a):
    """Picotes do ntsc_noise_light.gdshader (dashes): riscos horizontais de 2 linhas de video, em correntes de ate 3 pedacos de
    cor aleatoria, 4 a ~25 px de video, com a cor vazando para os lados. No shader eles ficam no rodape (densidade ~12,5*exp(-k/6,6));
    aqui a mesma densidade acompanha a faixa suave que desce (k = distancia em linhas de video ate o centro da faixa).
    Grade de video de 720 linhas (u_ratio = H/720), ruido renovado a 15 por segundo, SOMADO a imagem."""
    import cv2
    vh = 720
    vw = int(round(W * vh / H))
    fr = int(t * 15)
    rng = np.random.default_rng(fr * 7919 + 1)
    delta = np.zeros((vh, vw, 3), np.float32)
    center = ((t / a.periodo) % 1.0) * vh
    sigma = a.largura * vh
    amp = 0.7 * 0.5 * a.forca   # 0,7 (picote no rodape) x ntDashAmp (0,5)
    reach = int(sigma * 4)
    for pl in range(int((center - reach) // 2), int((center + reach) // 2) + 1):
        row = pl * 2
        if row < 0 or row + 1 >= vh:
            continue
        k = abs(row + 1 - center)
        pr = min(1.0, 12.5 * math.exp(-k / (sigma * 0.64)) / 8 * 0.8 / 1.2 * 0.6)
        for s in range(8):
            if rng.random() >= pr:
                continue
            xs = int(rng.random() * vw)
            for j in range(3):
                w = 2 + int(4 + 5.5 * (rng.random() + rng.random()) + 10 * rng.random() ** 3)
                r = rng.random()
                hue = (60 + 60 * rng.random()) if r < 0.3 else ((220 + 80 * rng.random()) if r < 0.6 else rng.random() * 360)
                rgb = colorsys.hsv_to_rgb(hue / 360, 0.35 + 0.40 * rng.random(), 0.70 + 0.30 * rng.random())
                tc = np.array(rgb, np.float32) * 255 - 128.6
                x0, x1 = max(0, xs), min(vw, xs + w)
                if x1 > x0:
                    delta[row:row + 2, x0:x1] += tc * amp
                if rng.random() >= 0.45:
                    break
                xs += w + int(rng.random() * 3)
    delta = cv2.GaussianBlur(delta, (0, 0), sigmaX=2.5, sigmaY=1.4) * 1.6   # cor vazando para os lados e para as linhas vizinhas
    return cv2.resize(delta, (W, H), interpolation=cv2.INTER_LINEAR)

def misturar(r, p, rgba, n, t, a):
    if a.modo == 'picotes':
        H, W = rgba.shape[:2]
        out = rgba.copy()
        out[..., :3] = np.clip(rgba[..., :3].astype(np.float32) + picotes(W, H, t, a), 0, 255).astype(np.uint8)
        out[..., 3] = 255
        return out
    H = rgba.shape[0]
    noisy = ruido(r, p, rgba, n, a)
    m = mascara(t, H, a.periodo, a.largura, a.forca)
    out = rgba.astype(np.float32) * (1 - m) + noisy.astype(np.float32) * m
    out[..., 3] = 255
    return out.astype(np.uint8)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input'); ap.add_argument('output')
    ap.add_argument('--t', type=float, default=0.0, help='instante (imagem)')
    ap.add_argument('--periodo', type=float, default=6.667)
    ap.add_argument('--largura', type=float, default=0.0144)
    ap.add_argument('--forca', type=float, default=1.0)
    ap.add_argument('--modo', choices=['picotes', 'ruido'], default='picotes', help='picotes (padrao) ou ruido NTSC cheio')
    ap.add_argument('--zoom', type=int, default=4, help='tamanho do grao: 4 = quatro vezes maior')
    ap.add_argument('--fps', type=float, default=0)
    a = ap.parse_args()
    p = rv.fresh(PRESET); p['_anim'] = None
    mkr = (lambda w, h: None) if a.modo == 'picotes' else (lambda w, h: rv.Renderer(max(2, w // a.zoom), max(2, h // a.zoom)))
    if a.input.lower().endswith(('.png', '.jpg', '.jpeg')):
        from PIL import Image
        im = np.asarray(Image.open(a.input).convert('RGBA'), np.uint8)
        r = mkr(im.shape[1], im.shape[0])
        Image.fromarray(misturar(r, p, im, int(a.t * 15), a.t, a), 'RGBA').save(a.output)
        print('ok', a.output); return
    import av
    from fractions import Fraction
    inp = av.open(a.input); vs = inp.streams.video[0]
    W, H = vs.codec_context.width, vs.codec_context.height
    fps = a.fps or float(vs.average_rate or 30)
    r = mkr(W, H)
    out = av.open(a.output, 'w'); rate = Fraction(fps).limit_denominator(1000)
    ov = out.add_stream('libx264', rate=rate); ov.width, ov.height, ov.pix_fmt = W & ~1, H & ~1, 'yuv420p'
    ov.options = {'crf': '16', 'preset': 'medium'}
    ains = inp.streams.audio[0] if inp.streams.audio else None
    aout = out.add_stream_from_template(ains) if ains is not None else None
    n = 0
    for pkt in inp.demux(*([vs] + ([ains] if ains is not None else []))):
        if ains is not None and pkt.stream == ains:
            if pkt.dts is not None: pkt.stream = aout; out.mux(pkt)
            continue
        for fr in pkt.decode():
            res = misturar(r, p, fr.to_ndarray(format='rgba'), n * 15 // int(round(fps)) if False else int(n / fps * 15), n / fps, a)[:H & ~1, :W & ~1]
            vf = av.VideoFrame.from_ndarray(np.ascontiguousarray(res), format='rgba'); vf.pts, vf.time_base = n, 1 / rate
            for op in ov.encode(vf): out.mux(op)
            n += 1
    for op in ov.encode(): out.mux(op)
    out.close(); inp.close(); print('ok', a.output, n, 'quadros')

if __name__ == '__main__':
    main()
