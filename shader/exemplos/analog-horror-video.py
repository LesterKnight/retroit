#!/usr/bin/env python3
"""Exemplo real: pos-processamento do Reel Mansao 468 (9:16, 30 fps) so com o RETROit.

  python shader/exemplos/analog-horror-video.py entrada.mp4 saida.mp4 [--segundos 8] [--varredura 8]

Cadeia (ordem real das etapas): NTSC do jogo -> distorcao (jitter, onda, linhas repetidas em varredura) -> fita magnetica -> JPEG.
Tudo renova a 15 fps. O preset estatico fica em reel-mansao-definitivo.json; este script acrescenta o que muda no tempo
(fases do jitter e da onda, posicao da varredura), que o JSON de um quadro so nao guarda. Sai sem audio. Nunca usa a etapa "meta".
"""
import argparse, importlib.util, json, os
from fractions import Fraction
import numpy as np, av

HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location('rv', os.path.join(HERE, '..', 'retroit-video.py'))
rv = importlib.util.module_from_spec(sp); sp.loader.exec_module(rv)
PAD_PADRAO = 60   # margem com borda replicada (so quando o preset nao tem dsEdge > 0): a onda nao mostra a borda do quadro


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('entrada'); ap.add_argument('saida')
    ap.add_argument('--segundos', type=float, default=0, help='so os primeiros N segundos (0 = o video todo)')
    ap.add_argument('--varredura', type=float, default=8, help='segundos para a varredura ir de cima a baixo')
    ap.add_argument('--crf', type=int, default=14)
    a = ap.parse_args()
    P = rv.load_preset(os.path.join(HERE, 'reel-mansao-definitivo.json'), None)
    inp = av.open(a.entrada); vs = inp.streams.video[0]
    W, H = vs.codec_context.width, vs.codec_context.height
    fps = float(vs.average_rate)
    PAD = 0 if P.get('dsEdge', 0) > 0 else PAD_PADRAO   # dsEdge (1 repete, 2 espelha) faz o shader preencher a borda; sem margem
    r = rv.Renderer(W + 2 * PAD, H)
    out = av.open(a.saida, 'w'); rate = Fraction(fps).limit_denominator(1000)
    v = out.add_stream('libx264', rate=rate); v.width, v.height, v.pix_fmt, v.options = W & ~1, H & ~1, 'yuv420p', {'crf': str(a.crf)}
    ate = int(a.segundos * fps) if a.segundos else 10 ** 9
    for n, f in enumerate(inp.decode(video=0)):
        if n >= ate: break
        t = n / fps
        h = int(t * 15)                                  # indice do quadro a 15 fps
        q = dict(rv.preset_at(P, t))
        q['dsPhase'] = (h / 15 * 0.6) % 1                # jitter: sorteio novo a cada 1/15 s
        q['dsWavePhase'] = (h / 15 * 0.15) % 1           # onda lenta, fase propria
        q['dsLinePos'] = (t / a.varredura) % 1.0         # varredura das linhas repetidas
        rgba = np.pad(f.to_ndarray(format='rgba'), ((0, 0), (PAD, PAD), (0, 0)), mode='edge')
        with r.ctx:
            d = r.frame(rgba.tobytes(), n, q)
        d = np.frombuffer(d, np.uint8).reshape(H, W + 2 * PAD, 4)[:H & ~1, PAD:PAD + (W & ~1)]
        vf = av.VideoFrame.from_ndarray(np.ascontiguousarray(d), format='rgba'); vf.pts, vf.time_base = n, 1 / rate
        for op in v.encode(vf): out.mux(op)
        if n % 30 == 0: print('quadro', n, flush=True)
    for op in v.encode(): out.mux(op)
    out.close(); inp.close(); print('ok', a.saida)

if __name__ == '__main__':
    main()
