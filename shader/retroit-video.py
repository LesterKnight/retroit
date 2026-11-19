#!/usr/bin/env python3
"""RETROit em GPU (Caminho 2): preset (estatico ou animado, com a secao anim) -> imagem ou video.

  imagem:   python retroit-video.py foto.png saida.png --preset preset.json [--name "VHS locadora"]
  video:    python retroit-video.py video.mp4 saida.mp4 --preset preset.json
  imagem num instante do preset animado: ... --time 1.1 --frame-no 13
  fidelidade: python retroit-video.py --compare js.png gpu.png

Requer: python 3, numpy, pillow, moderngl; para video tambem PyAV (pip install av), que ja traz libx264, NVENC e aac.
O preset e o JSON que "Exportar JSON" do retroit.html grava (ou um preset solto).
"""
import argparse, json, math, os, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- preset (espelha DEF / fresh / sanitize do retroit.html) ----------
DEF = dict(pixel=4, down='box', bits=5, dither='bayer4', ditherAmt=1, gamma=1, lift=0, sat=1, contrast=1,
           tonR=1, tonG=1, tonB=1, halftone=0, dot=8, angle=45, scan=0, scanPx=0, crt=0, crtMask=.5, crtBloom=.4, crtCorner=.05, crtMaskW=3, crtMaskX=0, crtMaskH=0, crtMaskY=1, crtMaskYInt=.5, crtMaskR=1, crtLock=0, crtStagger=0, fpOn=0, fpLines=240, fpBlock=6, vig=0, noise=0, soft=0, alpha='hard',
           palette='snes', palColors=16, palDither=.5, ntOn=0, ntChroma=6, ntDelay=2, ntRing=.3, ntSmear=1,
           ntNoise=.08, ntGrain=2, ntCNoise=.04, ntSnow=.004, ntWave=3, ntVary=0, ntRs=0, ntPhase=0, ntHeadH=0, ntHeadShift=6, ntChromaV=0, ntInterlace=0, ntBand=0, ntLumaV=0, ntTrackH=0, ntTrackSnow=0, ntEdge=0, ntFieldNoise=0, ntBurst=0, ntChromaGain=1, dsOn=0, dsBarrel=0, dsZoom=1, dsWaveX=0,
           dsWaveY=0, dsWaveFreq=4, dsGlitch=0, dsGlitchSize=12, dsRgb=0, dsJitter=0, dsPhase=0,
           tpOn=0, tpShift=5, tpSmear=7, tpGhost=.16, tpRing=.35, tpStreak=.5, jpOn=0, jpQ=35, jpPass=2, jpSub=2, jpSharp=0)
KEYS = ['color', 'pixel', 'palette', 'ntsc', 'distort', 'halftone', 'scan', 'vig', 'noise', 'crt', 'tape', 'jpeg', 'meta']
ZERO = ['halftone', 'scan', 'vig', 'noise', 'crt']
RANGES = dict(tpShift=(0, 12), tpSmear=(1, 16), tpGhost=(0, .5), tpRing=(0, 1), tpStreak=(0, 1), jpQ=(3, 100), jpPass=(1, 6), jpSub=(1, 4), jpSharp=(0, 1),
              pixel=(1, 16), bits=(1, 8), ditherAmt=(0, 1), soft=(0, 1), gamma=(.5, 2), lift=(0, .25), sat=(0, 2),
              contrast=(.5, 1.8), palColors=(2, 256), palDither=(0, 1),
              ntChroma=(0, 24), ntDelay=(0, 12), ntRing=(0, 1), ntSmear=(0, 6), ntNoise=(0, .3), ntGrain=(1, 6),
              ntCNoise=(0, .3), ntSnow=(0, .05), ntWave=(0, 12), ntPhase=(0, .6), ntHeadH=(0, 24), ntHeadShift=(0, 40), ntChromaV=(0, 12), ntInterlace=(0, 1), ntBand=(0, .5), ntLumaV=(0, 2), ntTrackH=(0, 40), ntTrackSnow=(0, 1), ntEdge=(0, 1), ntFieldNoise=(0, .5), ntBurst=(0, 1), ntChromaGain=(.5, 1.5), dsBarrel=(-.3, .3), dsZoom=(.8, 1.5),
              dsWaveX=(0, 40), dsWaveY=(0, 40), dsWaveFreq=(1, 40), dsGlitch=(0, 1), dsGlitchSize=(2, 80),
              dsRgb=(0, 20), dsJitter=(0, 12), dsPhase=(0, 1), halftone=(0, 1), dot=(3, 24), angle=(0, 90), scan=(0, .5), scanPx=(0, 16), crt=(0, 1), tonR=(0, 2), tonG=(0, 2), tonB=(0, 2), crtMask=(0, 1), crtBloom=(0, 1), crtCorner=(0, .2), crtMaskW=(1, 12), crtMaskX=(0, 4), crtMaskH=(0, 12), crtMaskY=(0, 12), crtMaskYInt=(0, 1), crtMaskR=(0, 3), crtLock=(0, 1), crtStagger=(0, 1), fpOn=(0, 1), fpLines=(60, 720), fpBlock=(3, 12),
              vig=(0, .8), noise=(0, .2))
INTS = ['jpQ', 'jpPass', 'jpSub', 'ntVary', 'ntTrackH', 'ntLumaV', 'ntChromaV', 'ntRs', 'ntHeadH', 'ntHeadShift', 'pixel', 'scanPx', 'bits', 'palColors', 'ntChroma', 'ntDelay', 'ntSmear', 'ntGrain', 'ntWave']
PALS = json.load(open(os.path.join(HERE, 'palettes.json'), encoding='utf-8'))


def load_preset(path, name=None):
    j = json.load(open(path, encoding='utf-8'))
    if isinstance(j, dict) and 'presets' in j:
        ps = j['presets']
        if not ps:
            sys.exit('preset: arquivo sem presets')
        if name is None:
            name = next(iter(ps))
        if name not in ps:
            sys.exit('preset "%s" nao existe; ha: %s' % (name, ', '.join(ps)))
        o = ps[name]
    else:
        o = j
    p = fresh(o)
    p['_anim'] = o.get('anim')
    return p



def legacy_color(o):
    """Perfis antigos: tint, sepia e poster saíram; viram ganhos RGB e saturação (aproximados), como no app."""
    if not (o.get('tint') or o.get('sepia') or 'poster' in o):
        return o
    p = dict(o)
    sat, r, g, b = float(p.get('sat', 1)), float(p.get('tonR', 1)), float(p.get('tonG', 1)), float(p.get('tonB', 1))
    t, s = float(p.get('tint', 0) or 0), float(p.get('sepia', 0) or 0)
    if t > 0:
        r *= 1 - .25 * t; g *= 1 - .075 * t; b *= 1 + .175 * t
    if s > 0:
        sat *= 1 - .85 * s; r *= 1 + .13 * s; g *= 1 - .06 * s; b *= 1 - .32 * s
    if t > 0 or s > 0:
        p.update(sat=round(sat, 3), tonR=round(r, 3), tonG=round(g, 3), tonB=round(b, 3))
    for k in ('tint', 'sepia', 'poster'):
        p.pop(k, None)
    return p

def fresh(o):
    o = legacy_color(o)
    p = dict(DEF)
    for k, d in DEF.items():
        if k in o:
            v = o[k]
            if isinstance(d, str):
                if isinstance(v, str):
                    p[k] = v
            else:
                try:
                    n = float(v)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(n):
                    if k in RANGES:
                        n = min(RANGES[k][1], max(RANGES[k][0], n))
                    p[k] = int(round(n)) if k in INTS else n
    if p['dither'] not in ('bayer4', 'bayer8', 'none'):
        p['dither'] = DEF['dither']
    if p['down'] not in ('box', 'nearest'):
        p['down'] = 'box'
    if p['alpha'] not in ('hard', 'soft'):
        p['alpha'] = 'hard'
    order = [k for k in o.get('order', []) if k in KEYS]
    order = [k for k in order if k != 'meta']
    order += [k for k in KEYS if k not in order and k != 'meta']
    p['order'] = order
    if isinstance(o.get('off'), list):
        off = [k for k in o['off'] if k in KEYS]
    else:
        off = []
        if 'palette' not in o: off.append('palette')
        if not o.get('ntOn'): off.append('ntsc')
        if not o.get('dsOn'): off.append('distort')
        if not o.get('tpOn'): off.append('tape')
        if not o.get('jpOn'): off.append('jpeg')
    for k in ZERO:
        if not p[k] > 0 and k not in off:
            off.append(k)
    if p['palette'] not in PALS:
        p['palette'] = 'snes'
        if 'palette' not in off: off.append('palette')
    p['off'] = off
    return p


# ---------- paleta ----------
def rnd(x):
    return np.floor(np.asarray(x, dtype=np.float64) + .5)


def median_cut(s, n):
    boxes = [s]
    while len(boxes) < n:
        bi, best, bc = -1, 0, 0
        for i, b in enumerate(boxes):
            if len(b) < 2: continue
            r = b.max(0) - b.min(0)
            m = r.max()
            if m > best: best, bi, bc = m, i, int(r.argmax())
        if bi < 0: break
        b = boxes[bi]
        b = b[np.argsort(b[:, bc], kind='stable')]
        h = len(b) >> 1
        boxes[bi:bi + 1] = [b[:h], b[h:]]
    return [b.mean(0) for b in boxes]


def palette_for(p, rgba):
    d = PALS[p['palette']]
    if 'list' in d:
        return [tuple(c) for c in d['list']]
    px = rgba.reshape(-1, 4)
    step = max(1, len(px) // 20000)
    smp = px[::step]
    smp = smp[smp[:, 3] >= 128][:, :3].astype(np.float64)
    if not len(smp): return [(0, 0, 0)]
    bits = d['bits']
    l = (1 << bits) - 1
    out, seen = [], set()
    for c in median_cut(smp, min(p['palColors'], 1 << (bits * 3))):
        q = tuple(int(rnd(rnd(v / 255 * l) / l * 255)) for v in c)
        if q not in seen: seen.add(q); out.append(q)
    return out


# ---------- preset animado (mesma matematica do modo Animar em retroit.html) ----------
M32 = 0xFFFFFFFF
STEP1 = {'ntTrackH', 'ntLumaV', 'ntChromaV', 'ntHeadH', 'ntHeadShift', 'pixel', 'bits', 'palColors', 'ntChroma', 'ntDelay', 'ntSmear', 'ntGrain', 'ntWave', 'dsWaveX',
         'dsWaveY', 'dsWaveFreq', 'dsGlitchSize', 'dsRgb', 'dsJitter', 'dot', 'angle'}


def imul(a, b):
    return (a * b) & M32


def mulberry(a):
    st = [a & M32]

    def f():
        st[0] = (st[0] + 0x6D2B79F5) & M32
        a = st[0]
        t = imul(a ^ (a >> 15), 1 | a)
        t = ((t + imul(t ^ (t >> 7), 61 | t)) & M32) ^ t
        return ((t ^ (t >> 14)) & M32) / 4294967296
    return f


def str_hash(t):
    h = 2166136261
    for ch in t:
        h = imul(h ^ ord(ch), 16777619)
    return h


def jround(x):
    return math.floor(x + .5)


def smooth_path(r, K, loop, raw):
    v = [r() for _ in range(K + 1)]
    v[0] = 0
    v[K] = 0 if loop else 1
    x = min(raw, .999999) * K
    i = int(math.floor(x)); f = x - i
    sm = f * f * (3 - 2 * f)
    return v[i] + (v[i + 1] - v[i]) * sm


def rand_t(raw, dur, loop):  # transicao "aleatoria" geral: um caminho so, semente 42
    return smooth_path(mulberry(42), max(2, jround(dur * 2)), loop, raw)


def rand_path(k, raw, smooth, seed, dur, loop):  # caminho proprio de cada parametro
    rate = .5 + (1 - smooth) * 7.5
    s = (str_hash(k) ^ imul(int(seed) + 1, 2654435761)) & M32
    return smooth_path(mulberry(s), max(2, jround(dur * rate)), loop, raw)


def ease_fn(name, pts):
    if name == 'in': return lambda u: u * u
    if name == 'out': return lambda u: 1 - (1 - u) * (1 - u)
    if name == 'inout': return lambda u: 2 * u * u if u < .5 else 1 - 2 * (1 - u) * (1 - u)
    if name == 'custom' and pts:
        p0, p1, p2, p3 = pts

        def bez(u):
            if u <= p0[0]: return p0[1]
            if u >= p3[0]: return p3[1]
            def co(i):
                c = 3 * (p1[i] - p0[i]); b = 3 * (p2[i] - p1[i]) - c
                return p3[i] - p0[i] - c - b, b, c
            ax, bx, cx = co(0); ay, by, cy = co(1)
            lo, hi, t = 0.0, 1.0, .5
            for _ in range(24):
                t = (lo + hi) / 2
                x = ((ax * t + bx) * t + cx) * t + p0[0]
                if x < u: lo = t
                else: hi = t
            return ((ay * t + by) * t + cy) * t + p0[1]
        return bez
    return lambda u: u


class Anim:
    """Avalia o preset animado no tempo t (segundos): devolve o preset daquele quadro."""
    def __init__(self, base, anim):
        self.base, self.a = base, anim
        self.dur = max(.5, float(anim.get('duration', 3)))
        self.loop = bool(anim.get('loop', True))
        self.ease = ease_fn(anim.get('ease', 'linear'), anim.get('points'))

    def at(self, t):
        a, tr = self.a, self.a.get('transition', 'linear')
        raw = ((t % self.dur) / self.dur) if self.loop else min(t / self.dur, 1.0)
        if tr == 'random': e = rand_t(raw, self.dur, self.loop)
        else: e = self.ease((raw * 2 if raw < .5 else 2 - raw * 2) if tr == 'boomerang' else raw)
        o = {k: v for k, v in self.base.items() if not k.startswith('_')}
        tracks = a.get('tracks', {})
        for k, tk in tracks.items():
            if k.startswith('off:'): continue
            ek = rand_path(k, raw, tk.get('smooth', .5), tk.get('seed', 42), self.dur, self.loop)                 if tk.get('mode') == 'random' else e
            if tk.get('mode') == 'keys':   # quadros-chave: [tempo 0-1, valor], linear, parado fora dos pontos
                ks = tk['keys']
                if raw <= ks[0][0]: val = ks[0][1]
                elif raw >= ks[-1][0]: val = ks[-1][1]
                else:
                    i = 0
                    while ks[i + 1][0] < raw: i += 1
                    (ta, va), (tb, vb) = ks[i], ks[i + 1]
                    val = va + (vb - va) * (raw - ta) / (tb - ta)
                o[k] = jround(val) if k in STEP1 else val
                continue
            fr, to = tk['from'], tk['to']
            if tk.get('step') or not isinstance(fr, (int, float)):
                v = fr if ek < .5 else to
            else:
                v = fr + (to - fr) * ek
                if k in STEP1: v = jround(v)
            o[k] = v
        off = []
        for k in KEYS:
            if k == 'meta': continue
            tk = tracks.get('off:' + k)
            if tk:
                x, y = tk['from'] == 1, tk['to'] == 1
                v = (x if e < .5 else y) if x == y or k not in ZERO else False
            else:
                v = k in self.base['off']
            kt = tracks.get(k)
            if k in ZERO and kt and kt.get('mode') == 'keys' and any(q[1] > 0 for q in kt['keys']): v = False
            if v: off.append(k)
        o['off'] = off
        if a.get('orderTo') and e >= .5: o['order'] = a['orderTo']
        return fresh(o)


# ---------- GPU ----------
S = dict(color=0, pixdown=1, pixup=2, palette=3, ntsc=4, distort=5, halftone=6, scan=7, vig=8, noise=9, crt=10, tape=11)
VS = '#version 330\nvoid main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);gl_Position=vec4(p*2.-1.,0.,1.);}'



# ---------- Recompressao JPEG (so aqui, em numpy; nao existe no .frag): espelha jpegData() do retroit.html ----------
JQY = np.array([16,11,10,16,24,40,51,61,12,12,14,19,26,58,60,55,14,13,16,24,40,57,69,56,14,17,22,29,51,87,80,62,18,22,37,56,68,109,103,77,24,35,55,64,81,104,113,92,49,64,78,87,103,121,120,101,72,92,95,98,112,100,103,99], np.float32).reshape(8, 8)
JQC = np.full((8, 8), 99, np.float32)
JQC[:4, :4] = [[17,18,24,47],[18,21,26,66],[24,26,56,99],[47,66,99,99]]
JCOS = np.array([[(0.5 / math.sqrt(2) if u == 0 else 0.5) * math.cos((2 * x + 1) * u * math.pi / 16) for x in range(8)] for u in range(8)], np.float32)


def jq_table(base, q):
    sc = 5000 / q if q < 50 else 200 - 2 * q
    return np.clip(np.floor((base * sc + 50) / 100), 1, 255).astype(np.float32)


def jpeg_plane(pl, tb, ox, oy):
    h, w = pl.shape
    nby, nbx = -(-(h + oy) // 8), -(-(w + ox) // 8)
    pad = np.pad(pl, ((oy, nby * 8 - h - oy), (ox, nbx * 8 - w - ox)), mode='edge') - 128
    b = pad.reshape(nby, 8, nbx, 8).transpose(0, 2, 1, 3)
    f = np.einsum('ux,ijxy,vy->ijuv', JCOS, b, JCOS)
    f = np.floor(f / tb + .5) * tb
    r = np.einsum('ux,ijuv,vy->ijxy', JCOS, f, JCOS)
    out = r.transpose(0, 2, 1, 3).reshape(nby * 8, nbx * 8) + 128
    return out[oy:oy + h, ox:ox + w]


def jpeg_np(rgba, q, passes, sub, sharp):
    d = rgba.astype(np.float32)
    H, W = d.shape[:2]
    if sharp > 0:
        c = d[..., :3].copy(); pd = np.pad(c, ((1, 1), (1, 1), (0, 0)), mode='edge')
        blur = sum(pd[dy:dy + H, dx:dx + W] for dy in range(3) for dx in range(3)) / 9
        d[..., :3] = np.round(np.clip(c + sharp * 2 * (c - blur), 0, 255))
    tY, tC = jq_table(JQY, q), jq_table(JQC, q)
    s = max(1, int(round(sub)))
    for p in range(int(passes)):
        r, g, b = d[..., 0], d[..., 1], d[..., 2]
        Y = .299 * r + .587 * g + .114 * b
        cb = 128 - .168736 * r - .331264 * g + .5 * b
        cr = 128 + .5 * r - .418688 * g - .081312 * b
        ch, cw = -(-H // s), -(-W // s)
        if s > 1:
            def down(c):
                pd = np.pad(c, ((0, ch * s - H), (0, cw * s - W)), mode='edge')
                return pd.reshape(ch, s, cw, s).mean(axis=(1, 3))
            cb, cr = down(cb), down(cr)
        ox, oy = ((p * 3) % 8, (p * 5) % 8) if p else (0, 0)
        Y = jpeg_plane(Y, tY, ox, oy); cb = jpeg_plane(cb, tC, ox, oy); cr = jpeg_plane(cr, tC, ox, oy)
        if s > 1:
            cb = np.repeat(np.repeat(cb, s, 0), s, 1)[:H, :W]; cr = np.repeat(np.repeat(cr, s, 0), s, 1)[:H, :W]
        cb -= 128; cr -= 128
        d[..., 0] = np.round(Y + 1.402 * cr); d[..., 1] = np.round(Y - .344136 * cb - .714136 * cr); d[..., 2] = np.round(Y + 1.772 * cb)
        d[..., :3] = np.clip(d[..., :3], 0, 255)
    return d.astype(np.uint8)


class Renderer:
    """Uma passada por etapa. Os parametros podem mudar a cada quadro (preset animado)."""
    def __init__(self, W, H):
        import moderngl
        self.mgl = moderngl
        self.ctx = moderngl.create_standalone_context()
        self.W, self.H = W, H
        self.prog = self.ctx.program(vertex_shader=VS,
                                     fragment_shader=open(os.path.join(HERE, 'retroit.frag'), encoding='utf-8').read())
        self.vao = self.ctx.vertex_array(self.prog, [])
        self.ratio = max(1.0, W / 1600.0)
        self.tex = [self.mk(W, H), self.mk(W, H)]
        self.fbo = [self.ctx.framebuffer(color_attachments=[t]) for t in self.tex]
        self.smalls = {}
        self.pal = self.mk(256, 1)
        self.palN, self.pal_ready, self.pal_key = 1, True, None
        self.locked_key, self.locked_pal = None, None   # paleta adaptativa fixada para o video todo
        self.p, self.rpx = None, 1

    def mk(self, w, h):
        t = self.ctx.texture((w, h), 4)
        t.filter = (self.mgl.NEAREST, self.mgl.NEAREST)
        t.repeat_x = t.repeat_y = False
        return t

    def small_for(self, sw, sh):
        if (sw, sh) not in self.smalls:
            t = self.mk(sw, sh)
            self.smalls[(sw, sh)] = (t, self.ctx.framebuffer(color_attachments=[t]))
        return self.smalls[(sw, sh)]

    def set_palette(self, pal):
        pal = pal[:256]
        self.palN = len(pal)
        a = np.zeros((256, 4), np.uint8); a[:, 3] = 255
        a[:len(pal), :3] = np.array(pal, np.uint8)
        self.pal.write(a.tobytes())
        self.pal_ready = True

    def cpu_jpeg(self, cur):
        """Etapa JPEG: le a textura, roda em numpy e devolve para a textura (nao existe no .frag)."""
        p = self.p
        px = np.frombuffer(self.tex[cur].read(), np.uint8).reshape(self.H, self.W, 4)
        self.tex[cur].write(np.ascontiguousarray(jpeg_np(px, p['jpQ'], p['jpPass'], p['jpSub'], p['jpSharp'])).tobytes())
        return cur

    def u(self, name, v):
        if name in self.prog: self.prog[name].value = v

    def static(self):
        p = self.p
        for k in DEF:
            v = p.get(k)
            if k in ('down', 'dither', 'alpha', 'palette', 'ntOn', 'dsOn'): continue
            if k in INTS: self.u(k, int(v))
            elif isinstance(v, (int, float)): self.u(k, float(v))
        self.u('down', 0 if p['down'] == 'box' else 1)
        self.u('dither', {'none': 0, 'bayer4': 1, 'bayer8': 2}[p['dither']])
        self.u('alpha', 0 if p['alpha'] == 'hard' else 1)
        self.u('u_full', (self.W, self.H)); self.u('u_ratio', float(self.ratio))
        self.u('u_rpx', int(self.rpx)); self.u('u_dot', float(max(2.0, p['dot'] * self.ratio)))
        self.u('u_pixOff', 1 if 'pixel' in p['off'] else 0)
        self.u('u_palN', int(self.palN)); self.u('u_seed', 42)
        self.u('u_tex', 0); self.u('u_pal', 1)

    def run(self, src, dst_fbo, size, stage):
        src.use(0); self.pal.use(1)
        self.u('u_stage', stage); self.u('u_out', size)
        dst_fbo.use(); self.ctx.viewport = (0, 0, size[0], size[1])
        self.vao.render(self.mgl.TRIANGLES, vertices=3)

    def palette_input(self, rgba_bytes, n, p):
        """Pixels que chegam na etapa Paleta (depois das etapas anteriores), para amostrar a paleta adaptativa."""
        self.p = p
        self.rpx = max(1, int(rnd(p['pixel'] * self.ratio)))
        sw, sh = max(1, -(-self.W // self.rpx)), max(1, -(-self.H // self.rpx))
        small, sfbo = self.small_for(sw, sh)
        self.static(); self.u('u_frame', n)
        self.tex[0].write(rgba_bytes)
        cur = 0
        for k in p['order']:
            if k == 'palette': break
            if k == 'meta' or k in p['off']: continue
            if k == 'jpeg':
                cur = self.cpu_jpeg(cur); continue
            if k == 'pixel':
                self.run(self.tex[cur], sfbo, (sw, sh), S['pixdown']); nxt = 1 - cur
                self.run(small, self.fbo[nxt], (self.W, self.H), S['pixup']); cur = nxt
                continue
            nxt = 1 - cur
            self.run(self.tex[cur], self.fbo[nxt], (self.W, self.H), S[k]); cur = nxt
        return np.frombuffer(self.tex[cur].read(), np.uint8).reshape(-1, 4)

    def lock_palette(self, p, samples):
        pal = palette_for(p, samples)
        self.locked_key = (p['palette'], p['palColors']); self.locked_pal = pal
        self.pal_key = None   # forca a reaplicar no proximo quadro

    def frame(self, rgba_bytes, n, p):
        self.p = p
        self.rpx = max(1, int(rnd(p['pixel'] * self.ratio)))
        sw, sh = max(1, -(-self.W // self.rpx)), max(1, -(-self.H // self.rpx))
        small, sfbo = self.small_for(sw, sh)
        # paleta: lista fixa troca na hora; adaptativa (median cut) e refeita quando a paleta ou N mudam
        if 'palette' not in p['off']:
            key = (p['palette'], p['palColors'] if 'list' not in PALS[p['palette']] else 0)
            if key != self.pal_key:
                self.pal_key = key
                self.pal_ready = False
                if 'list' in PALS[p['palette']]:
                    self.set_palette(palette_for(p, None))
                elif key == self.locked_key:
                    self.set_palette(self.locked_pal)
        self.static()
        self.u('u_frame', n)
        self.tex[0].write(rgba_bytes)
        cur = 0
        for k in p['order']:
            if k == 'meta' or k in p['off']: continue
            if k == 'pixel':
                self.run(self.tex[cur], sfbo, (sw, sh), S['pixdown'])
                nxt = 1 - cur
                self.run(small, self.fbo[nxt], (self.W, self.H), S['pixup']); cur = nxt
                continue
            if k == 'jpeg':
                cur = self.cpu_jpeg(cur); continue
            if k == 'palette' and not self.pal_ready:
                # paleta adaptativa: median cut sobre o resultado das etapas anteriores
                px = np.frombuffer(self.tex[cur].read(), np.uint8).reshape(-1, 4)
                self.set_palette(palette_for(p, px))
            self.u('u_palN', int(self.palN))
            nxt = 1 - cur
            self.run(self.tex[cur], self.fbo[nxt], (self.W, self.H), S[k]); cur = nxt
        return self.fbo[cur].read(components=4)


# ---------- entrada/saida ----------
def preset_at(p, t):
    an = p.get('_anim')
    return Anim(p, an).at(t) if an else p


def do_image(a):
    from PIL import Image
    im = Image.open(a.input).convert('RGBA')
    W, H = im.size
    if W > 1600:
        print('aviso: imagem maior que 1600 px; os px do preset serao escalados por W/1600 (como em video)')
    p = load_preset(a.preset, a.name)
    data = np.asarray(im, np.uint8)
    r = Renderer(W, H)
    out = np.frombuffer(r.frame(data.tobytes(), a.frame_no, preset_at(p, a.time)), np.uint8).reshape(H, W, 4)
    Image.fromarray(out, 'RGBA').save(a.output)
    print('ok', a.output)


def do_video(a):
    """Video com PyAV (traz libx264, NVENC e aac; nao precisa de ffmpeg no PATH). O audio e copiado do original."""
    import av
    from fractions import Fraction
    inp = av.open(a.input)
    vs = inp.streams.video[0]
    W, H = vs.codec_context.width, vs.codec_context.height
    fps = a.fps or float(vs.average_rate or 30)
    W2, H2 = W & ~1, H & ~1   # yuv420p exige dimensoes pares
    p = load_preset(a.preset, a.name)
    an = Anim(p, p['_anim']) if p.get('_anim') else None
    r = Renderer(W, H)
    # paleta adaptativa: uma so para o video, por amostragem de quadros espalhados (nao pisca entre cenas)
    p0 = an.at(0) if an else p
    if 'palette' not in p0['off'] and 'list' not in PALS[p0['palette']]:
        total = vs.frames or int(float(inp.duration or 0) / 1e6 * fps) or 1
        K = min(a.palette_frames, total)
        want = {int(j * total / K) for j in range(K)}
        smp, n0 = [], 0
        for fr in inp.decode(video=0):
            if n0 in want:
                pt = an.at(n0 / fps) if an else p
                if 'palette' not in pt['off']:
                    px = r.palette_input(fr.to_ndarray(format='rgba').tobytes(), n0, pt)
                    smp.append(px[::max(1, len(px) // 20000)])
            n0 += 1
        if smp: r.lock_palette(p0, np.concatenate(smp))
        inp.close(); inp = av.open(a.input); vs = inp.streams.video[0]
    out = av.open(a.output, 'w')
    rate = Fraction(fps).limit_denominator(1000)

    def add_video(codec, opts):
        s = out.add_stream(codec, rate=rate)
        s.width, s.height, s.pix_fmt, s.options = W2, H2, 'yuv420p', opts
        return s
    try:
        ovs = add_video('h264_nvenc', {'preset': 'p7', 'rc': 'vbr', 'cq': str(a.cq)})
        ovs.encode(av.VideoFrame(W2, H2, 'yuv420p'))   # testa se a placa aceita; senao cai no libx264
    except Exception:
        out.close(); out = av.open(a.output, 'w')
        ovs = add_video('libx264', {'crf': str(a.cq), 'preset': 'medium'})
    ains = inp.streams.audio[0] if inp.streams.audio else None
    aout = out.add_stream_from_template(ains) if ains is not None else None
    n = 0
    for pkt in inp.demux(*([vs] + ([ains] if ains is not None else []))):
        if ains is not None and pkt.stream == ains:
            if pkt.dts is not None:
                pkt.stream = aout
                out.mux(pkt)
            continue
        for fr in pkt.decode():
            pt = an.at(n / fps) if an else p   # o preset animado repete a cada `duration` segundos se loop
            rgba = fr.to_ndarray(format='rgba')
            res = np.frombuffer(r.frame(rgba.tobytes(), n, pt), np.uint8).reshape(H, W, 4)[:H2, :W2]
            vf = av.VideoFrame.from_ndarray(np.ascontiguousarray(res), format='rgba')
            vf.pts, vf.time_base = n, 1 / rate
            for op in ovs.encode(vf): out.mux(op)
            n += 1
            if a.max_frames and n >= a.max_frames: break
        if a.max_frames and n >= a.max_frames: break
    for op in ovs.encode(): out.mux(op)
    out.close(); inp.close()
    print('ok', a.output, n, 'quadros', '(%s)' % ovs.codec_context.name)


def do_compare(x, y):
    from PIL import Image
    A = np.asarray(Image.open(x).convert('RGBA'), np.float64)
    B = np.asarray(Image.open(y).convert('RGBA'), np.float64)
    if A.shape != B.shape: sys.exit('tamanhos diferentes: %s x %s' % (A.shape, B.shape))
    d = np.abs(A - B).mean((0, 1))
    print('diferenca media por canal (R G B A): %.3f %.3f %.3f %.3f / 255 (meta < 2)' % tuple(d))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('input', nargs='?'); ap.add_argument('output', nargs='?')
    ap.add_argument('--preset'); ap.add_argument('--name')
    ap.add_argument('--frame-no', dest='frame_no', type=int, default=0, help='numero do quadro (semente do ruido)')
    ap.add_argument('--time', type=float, default=0.0, help='imagem: instante (s) do preset animado')
    ap.add_argument('--fps', type=float); ap.add_argument('--cq', type=int, default=19)
    ap.add_argument('--max-frames', dest='max_frames', type=int, default=0)
    ap.add_argument('--palette-frames', dest='palette_frames', type=int, default=24, help='quadros amostrados para a paleta adaptativa do video')
    ap.add_argument('--compare', nargs=2, metavar=('JS_PNG', 'GPU_PNG'))
    a = ap.parse_args()
    if a.compare: do_compare(*a.compare)
    elif a.input and a.output and a.preset:
        (do_image if os.path.splitext(a.input)[1].lower() in ('.png', '.jpg', '.jpeg', '.webp', '.bmp') else do_video)(a)
    else:
        ap.print_help()
