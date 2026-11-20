#!/usr/bin/env python3
"""Pos-render do Reel Mansao 468 + aviso guerra fria, com o preset DEFINITIVO do RETROit em todos os quadros.

  python montar-final.py final_bruto.mp4 saida.mp4 [--de A --ate B --sem-audio --log arq.log]

Cadeia (exemplos/reel-mansao-definitivo.json): NTSC do jogo -> distorcao (jitter, onda lenta, varredura de linhas repetidas de 8 s)
-> fita magnetica -> JPEG. Tudo renova a 15 fps. Mesmo preset no video inteiro (aviso incluso). Nunca usa a etapa meta.
O audio e copiado do original. --aviso-ini e aceito e ignorado (compatibilidade com o .bat).
"""
import argparse, importlib.util, os, time
from fractions import Fraction
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location('rv', os.path.join(HERE, 'retroit-video.py'))
rv = importlib.util.module_from_spec(sp); sp.loader.exec_module(rv)
PAD_PADRAO = 60   # margem com borda replicada (so quando o preset nao tem dsEdge > 0): a onda nao mostra a borda do quadro
VARREDURA = 8.0   # s para a varredura ir de cima a baixo
LOG = None


def say(*x):
    print(*x, flush=True)
    if LOG:
        with open(LOG, 'a', encoding='utf8') as f: print(*x, file=f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input'); ap.add_argument('output')
    ap.add_argument('--aviso-ini', type=int, default=0, help='ignorado')
    ap.add_argument('--cq', type=int, default=16)
    ap.add_argument('--de', type=int, default=0, help='primeiro quadro desta parte')
    ap.add_argument('--ate', type=int, default=10**9, help='quadro final (exclusivo) desta parte')
    ap.add_argument('--sem-audio', action='store_true', help='parte para juntar depois: sem audio')
    ap.add_argument('--log', help='arquivo onde tambem gravar o andamento')
    a = ap.parse_args()
    global LOG; LOG = a.log
    if a.log: open(a.log, 'w').close()
    import av
    inp = av.open(a.input); vs = inp.streams.video[0]
    W, H = vs.codec_context.width, vs.codec_context.height
    fps = float(vs.average_rate)
    P = rv.load_preset(os.path.join(HERE, 'exemplos', 'reel-mansao-definitivo.json'), None)
    PAD = 0 if P.get('dsEdge', 0) > 0 else PAD_PADRAO   # dsEdge (1 repete, 2 espelha) faz o shader preencher a borda; sem margem
    r = rv.Renderer(W + 2 * PAD, H)
    out = av.open(a.output, 'w'); rate = Fraction(fps).limit_denominator(1000)

    def add_video(codec, opts):
        v = out.add_stream(codec, rate=rate); v.width, v.height, v.pix_fmt, v.options = W & ~1, H & ~1, 'yuv420p', opts
        return v
    try:   # NVENC; sem sessao livre ou placa, cai no libx264
        t = av.CodecContext.create('h264_nvenc', 'w')
        t.width, t.height, t.pix_fmt, t.time_base = W & ~1, H & ~1, 'yuv420p', Fraction(1, 30)
        t.options = {'preset': 'p7', 'rc': 'vbr', 'cq': str(a.cq)}
        t.open(); t.encode(av.VideoFrame(W & ~1, H & ~1, 'yuv420p')); del t
        ov = add_video('h264_nvenc', {'preset': 'p7', 'rc': 'vbr', 'cq': str(a.cq)})
    except Exception:
        ov = add_video('libx264', {'crf': str(a.cq), 'preset': 'medium'})
    ains = inp.streams.audio[0] if (inp.streams.audio and not a.sem_audio) else None
    aout = out.add_stream_from_template(ains) if ains is not None else None
    n = 0; t0 = time.time(); total = min(a.ate, vs.frames or a.ate) - a.de
    for pkt in inp.demux(*([vs] + ([ains] if ains is not None else []))):
        if ains is not None and pkt.stream == ains:
            if pkt.dts is not None: pkt.stream = aout; out.mux(pkt)
            continue
        for fr in pkt.decode():
            if n < a.de: n += 1; continue
            if n >= a.ate: break
            t = n / fps; h = int(t * 15)
            q = dict(rv.preset_at(P, t))
            q['dsPhase'] = (h / 15 * 0.6) % 1          # jitter: sorteio novo a cada 1/15 s
            q['dsWavePhase'] = (h / 15 * 0.15) % 1     # onda lenta, fase propria
            q['dsLinePos'] = (t / VARREDURA) % 1.0     # varredura das linhas repetidas
            rgba = np.pad(fr.to_ndarray(format='rgba'), ((0, 0), (PAD, PAD), (0, 0)), mode='edge')
            with r.ctx:
                d = r.frame(rgba.tobytes(), n, q)
            res = np.frombuffer(d, np.uint8).reshape(H, W + 2 * PAD, 4)[:H & ~1, PAD:PAD + (W & ~1)]
            vf = av.VideoFrame.from_ndarray(np.ascontiguousarray(res), format='rgba'); vf.pts, vf.time_base = n - a.de, 1 / rate
            for op in ov.encode(vf): out.mux(op)
            n += 1
            k = n - a.de
            if k % 20 == 0 or n == a.ate:
                el = time.time() - t0; say('quadro %d/%d  %.0f s decorridos  faltam ~%.0f s' % (k, total, el, el / k * (total - k)))
    for op in ov.encode(): out.mux(op)
    out.close(); inp.close(); say('ok', a.output, n, 'quadros (%s)' % ov.codec_context.name)

if __name__ == '__main__':
    main()
