#version 330
// RETROit: todas as etapas num fragment shader só (Caminho 2, fase 1).
// O script roda UMA passada por etapa, na ordem do preset, escolhida por u_stage
// (etapas como NTSC e Distorção leem pixels vizinhos, então não cabem num laço de uma passada).
// Entrada e saída em sRGB (bytes), RGBA8 entre as passadas, como o canvas do JS.
// Nomes dos uniforms = chaves do preset JSON (ver spec/Formato do preset.md).
// Referência numérica: a versão JS em retroit.html (stColor, stPixel, ...).

uniform sampler2D u_tex;   // imagem de entrada da passada
uniform sampler2D u_pal;   // paleta, 256x1 (RGB em bytes)
uniform int   u_stage;     // ver S_* abaixo
uniform ivec2 u_out;       // tamanho da saída desta passada
uniform ivec2 u_full;      // tamanho da imagem de trabalho (W,H)
uniform int   u_frame;
uniform int   u_seed;
uniform int   u_rpx;       // R.px: pixel escalado pela resolução
uniform float u_dot;       // R.dot: ponto do halftone escalado
uniform float u_ratio;     // escala dos px (largura / 1600, mínimo 1)
uniform int   u_pixOff;    // 1 se a etapa Pixel está desligada
uniform int   u_palN;      // nº de cores em u_pal

// parâmetros do preset (mesmo nome das chaves)
uniform int   bits;  uniform int dither;  uniform float ditherAmt;  uniform float soft;
uniform int   down;  uniform int alpha;
uniform float gamma; uniform float lift;  uniform float sat; uniform float contrast;

uniform float palDither;
uniform int   ntChroma; uniform int ntDelay; uniform float ntRing; uniform int ntSmear;
uniform float ntNest; uniform int ntVary; uniform float ntChromaGain; uniform float ntEdge; uniform float ntFieldNoise; uniform float ntBurst; uniform int ntTrackH; uniform float ntTrackSnow; uniform float ntBand; uniform int ntLumaV; uniform int ntChromaV; uniform float ntInterlace; uniform int ntRs; uniform float ntPhase; uniform int ntHeadH; uniform int ntHeadShift; uniform float ntNoise;  uniform int ntGrain; uniform float ntCNoise; uniform float ntSnow; uniform int ntWave;
uniform float dsBarrel; uniform float dsZoom; uniform float dsWaveX; uniform float dsWaveY; uniform float dsWaveFreq;
uniform float dsGlitch; uniform float dsGlitchSize; uniform float dsRgb; uniform float dsJitter; uniform float dsPhase; uniform float dsWavePhase;
uniform float dsLineRep; uniform float dsLineCount; uniform float dsLineH; uniform float dsLineDev; uniform float dsLineDevRows; uniform float dsLinePos; uniform float dsEdge;
uniform float halftone; uniform float angle; uniform float tonR; uniform float tonG; uniform float tonB; uniform float crt; uniform float crtMask; uniform float crtBloom; uniform float crtCorner; uniform float crtMaskW; uniform float crtMaskX; uniform float crtMaskH; uniform float crtMaskY; uniform float crtMaskYInt; uniform float crtMaskR; uniform float crtLock; uniform float crtStagger;
uniform float scan; uniform int scanPx; /* scanPx: pixels por linha de TV (0 = automático) */ uniform float vig; uniform float noise;

uniform float tpShift; uniform float tpSmear; uniform float tpGhost; uniform float tpRing; uniform float tpStreak;

out vec4 o;

const int S_COLOR=0, S_PIXDOWN=1, S_PIXUP=2, S_PALETTE=3, S_NTSC=4, S_DISTORT=5,
          S_HALFTONE=6, S_SCAN=7, S_VIG=8, S_NOISE=9, S_CRT=10, S_TAPE=11;
const float PI=3.14159265358979;

const int B4[16]=int[16](0,8,2,10,12,4,14,6,3,11,1,9,15,7,13,5);
const int B8[64]=int[64](0,32,8,40,2,34,10,42,48,16,56,24,50,18,58,26,12,44,4,36,14,46,6,38,60,28,52,20,62,30,54,22,
  3,35,11,43,1,33,9,41,51,19,59,27,49,17,57,25,15,47,7,39,13,45,5,37,63,31,55,23,61,29,53,21);

// ---- util ----
uint hu(uint x){x^=x>>16;x*=0x7feb352dU;x^=x>>15;x*=0x846ca68bU;x^=x>>16;return x;}
float rnd(int a,int b,int c){ // 0..1, determinístico por (a,b,c,seed)
  uint h=hu(uint(a)*0x9E3779B1U^hu(uint(b)+0x85EBCA6BU^hu(uint(c)*0xC2B2AE35U+uint(u_seed))));
  return float(h>>8)/16777216.0;}
float rf(int a,int b){return rnd(a,b,u_frame);}
float rn(int a,int b){return rnd(a,b,ntVary==1?u_frame:0);} // ruído do NTSC: só varia por quadro com a flag
int rnd_i(float v){return int(floor(v+0.5));}   // Math.round
int scl(int v){return rnd_i(float(v)*u_ratio);}  // sc() do NTSC
ivec2 isz(){return textureSize(u_tex,0);}
vec4 F(ivec2 p){p=clamp(p,ivec2(0),isz()-1);return texelFetch(u_tex,p,0);}
float luma(vec3 c){return c.r*.299+c.g*.587+c.b*.114;}

// ---- cor ----
vec4 stColor(vec4 c){
  vec3 base=c.rgb;
  // tonalidade: um ganho por canal (0 a 2, padrao 1) aplicado aos valores originais, antes da gama; qualquer tom da combinacao RGB
  if(tonR!=1.||tonG!=1.||tonB!=1.) base=clamp(base*vec3(tonR,tonG,tonB),0.,1.);
  vec3 v=pow(base,vec3(gamma));
  float l=luma(v);
  v=vec3(l)+(v-vec3(l))*sat;
  v=(v-.5)*contrast+.5;
  if(lift!=0.) v=lift+v*(1.-lift);
  return vec4(clamp(v,0.,1.),c.a);}

// ---- pixel, passada 1: saída no tamanho pequeno (sw x sh); média por bloco + quantização + dither ----
vec4 stPixDown(ivec2 p){
  ivec2 W=u_full,S=u_out;
  vec4 c;
  if(down==1){ // nearest
    ivec2 q=((2*p+1)*W)/(2*S);
    c=F(q);
  }else{
    ivec2 a=(p*W)/S;
    ivec2 b=max(a+1,((p+1)*W)/S);
    b=min(b,W);a=min(a,W-1);b=max(b,a+1);
    vec4 acc=vec4(0);float wa=0.;
    for(int y=a.y;y<b.y;y++)for(int x=a.x;x<b.x;x++){vec4 t=F(ivec2(x,y));acc.rgb+=t.rgb*t.a;acc.a+=t.a;wa+=1.;}
    float aa=acc.a;
    c=vec4(aa>0.?acc.rgb/aa:vec3(0),aa/wa);
  }
  c.rgb=floor(c.rgb*255.+.5)/255.;c.a=floor(c.a*255.+.5)/255.; // o JS guarda a média em bytes
  float n=float((1<<bits)-1);
  int ms=dither==2?8:4;
  float da=dither==0?0.:ditherAmt;
  float mv=dither==2?(float(B8[(p.y%8)*8+(p.x%8)])+.5)/64.:(float(B4[(p.y%4)*4+(p.x%4)])+.5)/16.;
  float m=.5+(mv-.5)*da;
  vec3 q=clamp(floor(c.rgb*255./255.*n+m),0.,n)/n;
  float a=c.a;
  if(alpha==0) a=(c.a*255.>=128.)?1.:0.;
  return vec4(q,a);}

// ---- pixel, passada 2: amplia o pequeno (u_tex) para W x H ----
vec4 smallAt(ivec2 q){return F(q);}
vec4 stPixUp(ivec2 p){
  int px=u_rpx;
  vec4 nr=smallAt(p/px);
  if(soft<=0.) return nr;
  vec2 f=(vec2(p)+.5)/float(px)-.5;
  ivec2 i0=ivec2(floor(f));vec2 t=f-vec2(i0);
  vec4 bl=mix(mix(smallAt(i0),smallAt(i0+ivec2(1,0)),t.x),mix(smallAt(i0+ivec2(0,1)),smallAt(i0+ivec2(1,1)),t.x),t.y);
  float k=1.-soft*.75;
  return mix(bl,nr,k);}

// ---- paleta ----
vec3 palAt(int i){return texelFetch(u_pal,ivec2(i,0),0).rgb*255.;}
vec4 stPalette(ivec2 p,vec4 c){
  if(c.a*255.<1.) return c;
  int cell=u_pixOff==1?1:max(1,u_rpx);
  float amp=255./pow(float(u_palN),1./3.)*palDither;
  int cy=(p.y/cell)&3,cx=(p.x/cell)&3;
  float off=((float(B4[cy*4+cx])+.5)/16.-.5)*amp;
  vec3 rgb=clamp(c.rgb*255.+off,0.,255.);
  vec3 b=floor(rgb/8.)*8.+4.;
  int bi=0;float bd=1e9;
  for(int i=0;i<u_palN;i++){
    vec3 d=b-palAt(i);
    float e=d.r*d.r*.3+d.g*d.g*.59+d.b*d.b*.11;
    if(e<bd){bd=e;bi=i;}
  }
  return vec4(palAt(bi)/255.,c.a);}

// ---- NTSC / VHS (YIQ) ----
// Tudo em escala de bytes (0..255) como no JS.
vec3 toYIQ(vec3 c){return vec3(.299*c.r+.587*c.g+.114*c.b,.596*c.r-.274*c.g-.322*c.b,.211*c.r-.523*c.g+.312*c.b);}
int gdx;int gy;int gW;
vec3 yiqAt(int x){ // YIQ na linha atual, depois do deslocamento da onda de borda
  x=clamp(x,0,gW-1);
  int sx=clamp(x-gdx,0,gW-1);
  return toYIQ(texelFetch(u_tex,ivec2(sx,gy),0).rgb*255.);}
float ypAt(int x,int r1){ // luma depois do smear, ou do passa-baixa de banda (ntBand)
  if(ntBand>0.){
    float num=0.,den=0.;
    for(int i=-8;i<=8;i++){float h=(i==0)?2.*ntBand:sin(2.*PI*ntBand*float(i))/(PI*float(i)),w=.54+.46*cos(PI*float(i)/9.),c=h*w;num+=c*yiqAt(clamp(x+i,0,gW-1)).x;den+=c;}
    return num/den;}
  if(r1<1) return yiqAt(x).x;
  float s=0.;for(int k=-r1;k<=r1;k++)s+=yiqAt(x+k).x;return s/float(2*r1+1);}
float lumaRow(int x,int r1){ // luma da linha gy: banda ou smear, mais ringing
  float Y=ypAt(x,r1);
  if(ntRing>0.){int r2=max(1,scl(2));float s=0.;for(int k=-r2;k<=r2;k++)s+=ypAt(clamp(x+k,0,gW-1),r1);float bl=s/float(2*r2+1);Y=Y+ntRing*1.5*(Y-bl);}
  return Y;}
float vn(int gx,int y,int k){ // 3 linhas com pesos 1; 1,8; 1 (correlação vertical medida no ntsc-rs), reescalada para o desvio de uma linha só
  int a=max(0,y-1),b=min(isz().y-1,y+1);
  return (rn(gx,a*5+k)+1.8*rn(gx,y*5+k)+rn(gx,b*5+k)-1.9)*(2./sqrt(5.24));}
int rowShift(int y){ // deslocamento horizontal da linha: onda de borda, cabeça de fita e campo ímpar
  int d=0,wave=scl(ntWave);
  if(wave>0){float n=sin(float(y)*.11)*.5+sin(float(y)*.037+1.3)*.3+(rnd(y,7,ntVary==1?u_frame:0)-.5)*.4;d=rnd_i(n*float(wave));}
  if(ntRs==1&&ntHeadH>0){
    int hh=scl(ntHeadH),hsh=scl(ntHeadShift);float t=(float(y)-float(isz().y-hh))/float(hh);
    if(t>0.) d+=rnd_i(float(hsh)*t*t+(rn(y,8)-.5)*.3*float(hsh));
  }
  if(ntInterlace>0.&&(y&1)==1) d+=rnd_i(ntInterlace*3.*u_ratio);
  return d;}
vec3 hsv2rgbN(vec3 c){vec3 k=clamp(abs(mod(c.x*6.+vec3(0.,4.,2.),6.)-3.)-1.,0.,1.);return c.z*mix(vec3(1.),k,c.y);}
// Cometas aninhados (igual ao ntsc_noise_light do jogo): fileira de cometas de 3 cores numa linha de video perto do rodape, cada um com um menor na linha de cima. Soma em Y e croma.
void nestedFx(ivec2 p,inout float Y,inout vec2 iq){
  if(ntNest<=0.||rn(0,991)>=ntNest) return;
  int k=int(floor(float(isz().y-1-p.y)/u_ratio));
  int kk=1+int(floor(rn(0,990)*10.));
  int d=k-kk;
  if(d<0||d>1) return;
  int vx=int(floor(float(p.x)/u_ratio));
  for(int c=-1;c<=0;c++){
    int ci=vx/26+c;
    if(rn(ci,kk*7+3)>=.6) continue;
    float len=8.+16.*rn(ci,kk*7+4);
    float off=float(ci*26)+floor(rn(ci,kk*7+5)*26.*.5);
    float ln2=(d==0)?len:len*.55,o2=off+((d==0)?0.:len*.25);
    float u=(float(vx)-o2)/ln2;
    if(u<0.||u>=1.) continue;
    float h0=rn(ci,kk*7+6),h1=fract(h0+.17+.33*rn(ci,kk*7+7)),h2=fract(h1+.17+.33*rn(ci,kk*7+8));
    vec3 c0=toYIQ(hsv2rgbN(vec3(h0,.55,.95))*255.-vec3(128.6)),c1=toYIQ(hsv2rgbN(vec3(h1,.55,.95))*255.-vec3(128.6)),c2=toYIQ(hsv2rgbN(vec3(h2,.55,.95))*255.-vec3(128.6));
    vec3 tc=mix(mix(c0,c1,smoothstep(.15,.45,u)),c2,smoothstep(.55,.85,u));
    float a=(1.-u)*((d==0)?.8:.5);
    Y+=tc.x*a;iq+=tc.yz*a;
  }
}
vec4 stNtsc(ivec2 p){
  gW=isz().x;gy=p.y;int x=p.x;
  gdx=rowShift(p.y);
  int r1=scl(ntSmear);
  float Y;
  if(ntLumaV>0){ // borrão vertical da luma, cada linha com o seu deslocamento horizontal
    int hv=ntLumaV>=2?2:1;float num=0.,den=0.;
    for(int k=-hv;k<=hv;k++){
      int yy=clamp(p.y+k,0,isz().y-1);gy=yy;gdx=rowShift(yy);
      float wgt=(hv==1)?((k==0)?2.:1.):((k==0)?6.:(abs(k)==1?4.:1.));
      num+=wgt*lumaRow(x,r1);den+=wgt;}
    Y=num/den;gy=p.y;gdx=rowShift(p.y);
  }else Y=lumaRow(x,r1);
  int cr=scl(ntChroma),dl=scl(ntDelay);
  int xc=dl>0?max(0,x-dl):x;
  vec2 iq;
  int cv=scl(ntChromaV);
  if(cv>1){ // vazamento vertical: média de cv linhas (y-cv/2 .. y+cv/2-1), cada uma com o seu deslocamento horizontal
    int lo=-(cv/2),hi=cv-cv/2-1;vec2 acc=vec2(0);
    for(int kk=lo;kk<=hi;kk++){
      int yy=clamp(p.y+kk,0,isz().y-1);gy=yy;gdx=rowShift(yy);vec2 s=vec2(0);
      if(cr<1) s=yiqAt(xc).yz;
      else{for(int k=-cr;k<=cr;k++)s+=yiqAt(xc+k).yz;s/=float(2*cr+1);}
      acc+=s;}
    iq=acc/float(cv);gy=p.y;gdx=rowShift(p.y);
  }else{
    if(cr<1) iq=yiqAt(xc).yz;
    else{vec2 s=vec2(0);for(int k=-cr;k<=cr;k++)s+=yiqAt(xc+k).yz;iq=s/float(2*cr+1);}
  }
  iq*=ntChromaGain;
  if(ntEdge>0.){ // transitório do filtro na borda esquerda (perfil medido no ntsc-rs)
    int xi=int(floor(float(x)/u_ratio));
    if(xi<10){float S[10]=float[10](.105,.445,.877,1.185,1.295,1.257,1.166,1.085,1.031,1.007);Y*=1.+ntEdge*(S[xi]-1.);}
  }
  nestedFx(p,Y,iq);   // sob o ruido, como no jogo
  float fm=1.+ntFieldNoise*(((p.y&1)==1)?-1.:1.);
  float amp=ntNoise*255.*fm,ampc=ntCNoise*255.*fm;
  int g=max(1,scl(ntGrain)),gc=g*2;
  if(ntRs==1){ // ruído por hash correlacionado entre 3 linhas (igual ao JS)
    if(ntPhase>0.){ // uma rotação de croma por linha, vizinhança de 6 linhas (veios horizontais de cor)
      float a=0.;for(int i=-2;i<=3;i++){int yy=clamp(p.y+i,0,isz().y-1);float w=(i==-2||i==3)?1.:((i==-1||i==2)?2.:3.);a+=w*rn(0,yy*5+3);}
      float th=(a-6.)*(2./sqrt(28.))*ntPhase,c=cos(th),s2=sin(th);iq=vec2(iq.x*c-iq.y*s2,iq.x*s2+iq.y*c);
    }
    if(amp>0.) Y+=vn(x/g,p.y,0)*amp;
    if(ampc>0.){iq.x+=vn(x/gc,p.y,1)*ampc;iq.y+=vn(x/gc,p.y,2)*ampc;}
  }else{
    if(amp>0.) Y+=(rn(x/g,p.y*3+0)-.5)*2.*amp;
    if(ampc>0.){iq.x+=(rn(x/gc,p.y*3+1)-.5)*2.*ampc;iq.y+=(rn(x/gc,p.y*3+2)-.5)*2.*ampc;}
  }
  if(ntSnow>0.){ // no máximo um risco por linha
    float pr=min(1.,ntSnow*4.);
    if(rn(p.y,901)<pr){
      int x0=int(floor(rn(p.y,902)*float(gW)));
      int len=max(2,scl(int(floor(4.+rn(p.y,903)*26.))));
      if(x>=x0&&x<x0+len){float t=1.-float(x-x0)/float(len);Y=Y+(255.-Y)*t;iq*=1.-t;}
    }
  }
  if(ntBurst>0.&&rn(0,960)<ntBurst){ // rajada de ruído: 3 linhas com ruído forte quase na largura toda
    int th=scl(ntTrackH),rc=1+int(floor(rn(0,961)*float(max(1,isz().y-th-3))));
    int x0=int(floor(rn(0,962)*.15*float(gW))),span=int(floor((.75+rn(0,963)*.25)*float(gW)));
    int dy=p.y-rc;
    if(abs(dy)<=1&&x>=x0&&x<x0+span){float u=rn(x,p.y*7+8);Y+=clamp(2.5*(u-.5),0.,1.)*255.*((dy==0)?1.:.5);}
  }
  if(ntTrackH>0&&ntTrackSnow>0.){ // ruído de rastreio: faixa no rodapé (igual ao JS)
    int th=scl(ntTrackH);
    if(p.y>=isz().y-th){
      float sev=rn(p.y,950);sev*=sev;int gx=x/max(1,scl(3));
      if(rn(gx,p.y*7+4)<ntTrackSnow*sev*2.){
        float u=rn(gx,p.y*7+5);Y+=255.*u*u*u;
        iq.x+=(rn(gx,p.y*7+6)-.5)*160.;iq.y+=(rn(gx,p.y*7+7)-.5)*160.;
      }
    }
  }
  float i=iq.x,q=iq.y;
  vec3 rgb=vec3(Y+.956*i+.621*q,Y-.272*i-.647*q,Y-1.106*i+1.703*q);
  int sx=clamp(x-gdx,0,gW-1);
  float a=texelFetch(u_tex,ivec2(sx,gy),0).a;
  return vec4(clamp(rgb/255.,0.,1.),a);}

// ---- distorção ----
bool gotS;
vec4 getS(vec2 s){ // amostra nearest; fora da imagem => alpha<0
  ivec2 q=ivec2(floor(s+.5));
  if(dsEdge>.5){ // borda: 1 = repete a última coluna/linha, 2 = espelha (vai e volta)
    if(dsEdge<1.5) q=clamp(q,ivec2(0),u_full-1);
    else{ivec2 m=((q%(2*u_full))+2*u_full)%(2*u_full); q=ivec2(m.x>=u_full.x?2*u_full.x-1-m.x:m.x, m.y>=u_full.y?2*u_full.y-1-m.y:m.y);}}
  if(q.x<0||q.y<0||q.x>=u_full.x||q.y>=u_full.y){gotS=false;return vec4(0);}
  gotS=true;return texelFetch(u_tex,q,0);}
vec4 stDistort(ivec2 p){
  int W=u_full.x,H=u_full.y;
  float rt=u_ratio;
  float ax=dsWaveX*rt,ay=dsWaveY*rt,ph=(dsWavePhase>=0.?dsWavePhase:dsPhase)*2.*PI,rgb=dsRgb*rt;
  int slice=max(1,rnd_i(dsGlitchSize*rt));
  float cx=float(W)/2.,cy=float(H)/2.;
  float u=(float(p.x)-cx)/cx,v=(float(p.y)-cy)/cy;
  if(dsBarrel!=0.){float r2=u*u+v*v;float f=1.+dsBarrel*r2+dsBarrel*2.*r2*r2;u*=f;v*=f;}
  u/=dsZoom;v/=dsZoom;
  float sx=cx+u*cx,sy=cy+v*cy;
  if(ax!=0.) sx+=ax*sin(2.*PI*(float(p.y)/float(H))*dsWaveFreq+ph);
  if(ay!=0.) sy+=ay*sin(2.*PI*(float(p.x)/float(W))*dsWaveFreq+ph);
  if(dsGlitch>0.){
    int si=p.y/slice; int ps=int(floor(dsPhase*1000.+.5));
    bool on=rnd(si,11,ps)<dsGlitch;
    if(on) sx+=float(rnd_i((rnd(si,12,ps)-.5)*2.*float(W)*.12*dsGlitch));
  }
  if(dsJitter>0.) sx+=float(rnd_i((rnd(p.y,21,int(floor(dsPhase*1000.+.5)))-.5)*2.*dsJitter*rt));
  if(dsLineRep>0.5&&dsLineCount>0.){ // grupo: linha original, dsLineDevRows linhas deslocadas dsLineDev px (lado sorteado), depois dsLineRep linhas que copiam a original
    int R=max(1,rnd_i(dsLineRep)),bl=max(1,rnd_i(dsLineH*rt)),D=max(0,rnd_i(dsLineDevRows))*bl,gh=D+R*bl,ps2=int(floor(dsPhase*1000.+.5));
    int cnt=max(1,min(rnd_i(dsLineCount),u_full.y/gh));
    float sh=float(u_full.y)/float(cnt);
    int s=min(cnt-1,int(float(p.y)/sh));
    int g0=int(float(s)*sh+(dsLinePos>=0.?dsLinePos:rnd(s,41,ps2))*max(sh-float(gh),0.)); // dsLinePos 0..1: posição vertical fixa (anime 0→1 para o grupo cair); -1 = sorteada
    int k=p.y-g0;
    if(k>=0&&k<gh){
      if(k<D) sx+=(rnd(s,42,ps2)<.5?-1.:1.)*dsLineDev*rt*float(k/bl+1); // escadinha: cada linha de desvio anda mais que a anterior
      else sy+=float(g0+(k-D)%bl-p.y);
    }
  }
  vec4 g=getS(vec2(sx,sy));
  if(!gotS) return vec4(0);
  float r=g.r,b=g.b;
  if(rgb!=0.){
    vec4 gr=getS(vec2(sx-rgb,sy));r=gotS?gr.r:0.;
    vec4 gb=getS(vec2(sx+rgb,sy));b=gotS?gb.b:0.;
  }
  return vec4(r,g.g,b,g.a);}

// ---- halftone, linhas, vinheta, ruído ----
vec4 stHalftone(ivec2 p,vec4 c){
  float t=angle*PI/180.,ct=cos(t),st=sin(t),tp=2.*PI/u_dot;
  float x=float(p.x),y=float(p.y);
  float u=(x*ct+y*st)*tp,v=(-x*st+y*ct)*tp,cc=(cos(u)+cos(v)+2.)/4.;
  float tone=luma(c.rgb),ink=clamp((cc-tone)/.08+.5,0.,1.),f=1.-halftone*ink;
  return vec4(c.rgb*f,c.a);}
vec4 stScan(ivec2 p,vec4 c){
  float per=u_pixOff==1?4.:float(max(2,u_rpx*2));
  if(scanPx>0) per=float(max(2,int(floor(float(scanPx)*u_ratio+.5))*2));
  float f=1.-scan*(.5+.5*cos(float(p.y)*2.*PI/per));
  return vec4(c.rgb*f,c.a);}
vec4 stVig(ivec2 p,vec4 c){
  float vy=(float(p.y)/float(u_full.y)-.5)*2.,vx=(float(p.x)/float(u_full.x)-.5)*2.;
  float f=1.-vig*((vx*vx+vy*vy)/2.);
  return vec4(c.rgb*f,c.a);}
vec4 stNoise(ivec2 p,vec4 c){
  float nz=(rnd(p.x,p.y,u_frame)-.5)*noise;  // (rand-.5)*255*noise em bytes
  return vec4(clamp(c.rgb+nz,0.,1.),c.a);}

// ---- CRT: tudo em escala de pixel (nunca free style). Os cantos da tela andam em BLOCOS INTEIROS do tamanho do pixel do preset (rb); a curvatura e da etapa Distorcao,
// o bloom soma copias deslocadas em passos inteiros e a mascara e feita de celulas R, G, B com cantos arredondados de 1 a 3 px (pixel art).
// `crt` (0..1) escala tudo. crtLock=1 prende o triplete ao bloco do pixel: cada bloco vira 3 colunas.
vec3 crtSi(ivec2 q){
  if(q.x<0||q.y<0||q.x>=u_full.x||q.y>=u_full.y) return vec3(0.);
  return texelFetch(u_tex,q,0).rgb;}
vec4 stCrt(ivec2 p){
  int rb=u_pixOff==1?1:max(1,u_rpx);
  vec2 fl=vec2(u_full);
  ivec2 bp=p/rb,po=p-bp*rb;
  vec2 bc=(vec2(bp*rb)+float(rb)*.5)/fl*2.-1.;
  float cr=crt*crtCorner;
  vec2 uv=bc;   // sem curvatura: ela ja existe na etapa Distorcao (dsBarrel)
  if(abs(uv.x)>1.||abs(uv.y)>1) return vec4(0.,0.,0.,1.);
  vec2 q=max(abs(uv)-vec2(1.-cr),vec2(0.));
  if(length(q)>cr) return vec4(0.,0.,0.,1.);
  vec2 sp=(uv*.5+.5)*fl-.5;
  ivec2 so=ivec2(floor(sp/float(rb)))*rb+po;
  vec3 c=crtSi(so);
  int o1=rb,o2=2*rb;
  vec3 s1=crtSi(so+ivec2(o1,0))+crtSi(so-ivec2(o1,0))+crtSi(so+ivec2(0,o1))+crtSi(so-ivec2(0,o1));
  vec3 s2=crtSi(so+ivec2(o2,0))+crtSi(so-ivec2(o2,0))+crtSi(so+ivec2(0,o2))+crtSi(so-ivec2(0,o2));
  vec3 b=(c*2.+s1+s2*.5)/8.;
  vec3 rgb=c+crt*crtBloom*.9*max(b-.45,vec3(0.));
  float a=1.-crt*crtMask;
  int idx,cx,cw,ly=0,ch=0;
  bool inRow=true,gapx=false;
  if(crtLock>.5){
    int lx=(p.x+((crtStagger>.5&&(bp.y&1)==1)?rb/2:0))%rb;   // fileiras alternadas deslocadas meia celula (mascara de pontos)
    idx=min(2,(lx*3)/rb);
    int x0=(idx*rb)/3,x1=((idx+1)*rb)/3;
    cw=max(1,x1-x0);cx=lx-x0;
    int gxx=min(max(0,int(floor(crtMaskX+.5))),cw-1);   // separacao horizontal: os ultimos gxx pixels de cada coluna ficam apagados
    gapx=cx>=cw-gxx;cw-=gxx;
    int gy=clamp(int(floor(crtMaskY+.5)),0,rb-1);
    if(gy>0){ly=p.y%rb;ch=rb-gy;inRow=ly<ch;}
  }else{
    int mw=max(1,int(floor(crtMaskW+.5)));
    int mh=int(floor(crtMaskH+.5)),gy=max(0,int(floor(crtMaskY+.5)));
    int rowi=(mh>0&&gy>0)?p.y/(mh+gy):p.y/mw;
    int pw=mw+max(0,int(floor(crtMaskX+.5)));
    int px=p.x+((crtStagger>.5&&(rowi&1)==1)?(3*pw)/2:0);
    idx=(px/pw)%3;cw=mw;cx=px%pw;gapx=cx>=mw;
    if(mh>0&&gy>0){ly=p.y%(mh+gy);ch=mh;inRow=ly<mh;}
  }
  float cover=1.;
  int R=int(floor(crtMaskR+.5));
  if(R>0&&ch>0&&inRow&&!gapx){
    int dxc=min(cx,cw-1-cx),dyc=min(ly,ch-1-ly);
    if(dxc<R&&dyc<R){
      float d=length(vec2(float(R)-(float(dxc)+.5),float(R)-(float(dyc)+.5)));
      cover=floor(clamp(float(R)+.5-d,0.,1.)*2.+.5)/2.;}}
  vec3 m=vec3(a);
  float lit=mix(a,1.,cover);
  if(idx==0)m.r=lit; else if(idx==1)m.g=lit; else m.b=lit;
  if(gapx)m=vec3(a);
  if(!inRow) m*=1.-crt*crtMaskYInt*(crtStagger>.5?1.-.85*clamp(luma(c),0.,1.):1.);   // so no modo CRT (stagger): o vao entre fileiras fecha onde o pixel e claro (o feixe vaza para o vao); no LCD o vao e constante
  rgb*=m*(1.+crt*crtMask*.5);
  return vec4(clamp(rgb,0.,1.),1.);}


// Fita magnetica: croma deslocado em sentidos opostos e borrado na horizontal, eco da luminancia, halo nas bordas e riscos de cor.
// Espelha tapeData() do retroit.html (mesma ordem de clamp e mesmo hash por linha/quadro).
vec3 ycc(vec3 c){c*=255.;return vec3(.299*c.r+.587*c.g+.114*c.b,128.-.168736*c.r-.331264*c.g+.5*c.b,128.+.5*c.r-.418688*c.g-.081312*c.b);}
vec4 stTape(ivec2 p){
  int W=isz().x,sh=int(floor(tpShift+.5)),sm=max(1,int(floor(tpSmear+.5))),gd=max(1,int(floor(tpShift*1.2+.5)));
  vec4 c0=F(p);
  float a=0.,b=0.,y2=0.;
  int ha=sm/2,hb=(sm+2)/2;
  for(int k=0;k<sm;k++){int xi=clamp(p.x+k-ha,0,W-1);a+=ycc(F(ivec2(clamp(xi+sh,0,W-1),p.y)).rgb).y;}
  for(int k=0;k<sm+2;k++){int xi=clamp(p.x+k-hb,0,W-1);b+=ycc(F(ivec2(clamp(xi-sh-1,0,W-1),p.y)).rgb).z;}
  for(int k=0;k<5;k++)y2+=ycc(F(ivec2(clamp(p.x+k-2,0,W-1),p.y)).rgb).x;
  a/=float(sm);b/=float(sm+2);y2/=5.;
  float Y=ycc(c0.rgb).x,Ye=ycc(F(ivec2(clamp(p.x-gd,0,W-1),p.y)).rgb).x;
  float yv=Y+tpGhost*(Ye-Y)+tpRing*(Y-y2),u=a-128.,v=b-128.;
  if(tpStreak>0.&&rnd(p.y,7,u_frame)<.06*tpStreak){
    int x0=int(floor(rnd(p.y,8,u_frame)*float(max(1,W-60)))),n=20+int(floor(rnd(p.y,9,u_frame)*40.));
    if(p.x>=x0&&p.x<x0+n){u+=(rnd(p.y,10,u_frame)-.5)*50.;v+=(rnd(p.y,11,u_frame)-.5)*50.;}}
  return vec4(clamp(vec3(yv+1.402*v,yv-.344136*u-.714136*v,yv+1.772*u)/255.,0.,1.),c0.a);}


// ---- recompressão JPEG na GPU (porte do jpeg_np do retroit-video.py): uma passada = RGB→YCbCr (croma subamostrado s×s),
// blocos 8×8 (com deslocamento da grade), DCT, quantização, DCT inversa e volta para RGB. Uma passada por chamada (u_jpOff = grade).
const float JQY[64]=float[64](16.0,11.0,10.0,16.0,24.0,40.0,51.0,61.0,12.0,12.0,14.0,19.0,26.0,58.0,60.0,55.0,14.0,13.0,16.0,24.0,40.0,57.0,69.0,56.0,14.0,17.0,22.0,29.0,51.0,87.0,80.0,62.0,18.0,22.0,37.0,56.0,68.0,109.0,103.0,77.0,24.0,35.0,55.0,64.0,81.0,104.0,113.0,92.0,49.0,64.0,78.0,87.0,103.0,121.0,120.0,101.0,72.0,92.0,95.0,98.0,112.0,100.0,103.0,99.0);
const float JQC[64]=float[64](17.0,18.0,24.0,47.0,99.0,99.0,99.0,99.0,18.0,21.0,26.0,66.0,99.0,99.0,99.0,99.0,24.0,26.0,56.0,99.0,99.0,99.0,99.0,99.0,47.0,66.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0,99.0);
const float JC[64]=float[64](0.3535534,0.3535534,0.3535534,0.3535534,0.3535534,0.3535534,0.3535534,0.3535534,0.4903926,0.4157348,0.2777851,0.0975452,-0.0975452,-0.2777851,-0.4157348,-0.4903926,0.4619398,0.1913417,-0.1913417,-0.4619398,-0.4619398,-0.1913417,0.1913417,0.4619398,0.4157348,-0.0975452,-0.4903926,-0.2777851,0.2777851,0.4903926,0.0975452,-0.4157348,0.3535534,-0.3535534,-0.3535534,0.3535534,0.3535534,-0.3535534,-0.3535534,0.3535534,0.2777851,-0.4903926,0.0975452,0.4157348,-0.4157348,-0.0975452,0.4903926,-0.2777851,0.1913417,-0.4619398,0.4619398,-0.1913417,-0.1913417,0.4619398,-0.4619398,0.1913417,0.0975452,-0.2777851,0.4157348,-0.4903926,0.4903926,-0.4157348,0.2777851,-0.0975452);   // JC[u*8+x]
uniform float jpQ; uniform float jpSub; uniform float jpSharp; uniform ivec2 u_jpOff;
float jqT(float base){float q=jpQ;float sc=q<50.?5000./q:200.-2.*q;return clamp(floor((base*sc+50.)/100.),1.,255.);}
float jBlock(in float sm[64],int ix,int iy,bool isC){
  float T[64];
  for(int r=0;r<8;r++)for(int v=0;v<8;v++){float a=0.;for(int c=0;c<8;c++)a+=JC[v*8+c]*sm[r*8+c];T[r*8+v]=a;}
  float o=0.;
  for(int u=0;u<8;u++){
    float rv=0.;
    for(int v=0;v<8;v++){
      float f=0.;for(int r=0;r<8;r++)f+=JC[u*8+r]*T[r*8+v];
      float tb=jqT(isC?JQC[u*8+v]:JQY[u*8+v]);
      f=floor(f/tb+.5)*tb;
      rv+=JC[v*8+ix]*f;
    }
    o+=JC[u*8+iy]*rv;
  }
  return o;}
vec4 stJpeg(ivec2 p){
  int W=u_full.x,H=u_full.y;int s=max(1,int(floor(jpSub+.5)));
  ivec2 mx=ivec2(W-1,H-1);
  vec4 c0=texelFetch(u_tex,p,0);
  int ix=(p.x+u_jpOff.x)%8,iy=(p.y+u_jpOff.y)%8;
  int x0=p.x-ix,y0=p.y-iy;
  float sy_[64];
  for(int r=0;r<8;r++)for(int c=0;c<8;c++){
    vec3 q=texelFetch(u_tex,clamp(ivec2(x0+c,y0+r),ivec2(0),mx),0).rgb*255.;
    sy_[r*8+c]=.299*q.r+.587*q.g+.114*q.b-128.;}
  float Y=jBlock(sy_,ix,iy,false)+128.;
  ivec2 cp=p/s;ivec2 cd=(ivec2(W,H)+s-1)/s;
  int cix=(cp.x+u_jpOff.x)%8,ciy=(cp.y+u_jpOff.y)%8;
  int cx0=cp.x-cix,cy0=cp.y-ciy;
  float sb[64],sr[64];
  for(int r=0;r<8;r++)for(int c=0;c<8;c++){
    ivec2 cc=clamp(ivec2(cx0+c,cy0+r),ivec2(0),cd-1);
    vec3 m=vec3(0.);
    for(int j=0;j<s;j++)for(int i=0;i<s;i++)m+=texelFetch(u_tex,clamp(cc*s+ivec2(i,j),ivec2(0),mx),0).rgb;
    m*=255./float(s*s);
    sb[r*8+c]=128.-.168736*m.r-.331264*m.g+.5*m.b-128.;
    sr[r*8+c]=128.+.5*m.r-.418688*m.g-.081312*m.b-128.;}
  float cb=jBlock(sb,cix,ciy,true),cr=jBlock(sr,cix,ciy,true);
  vec3 rgb=vec3(Y+1.402*cr,Y-.344136*cb-.714136*cr,Y+1.772*cb);
  return vec4(clamp(floor(rgb+.5),0.,255.)/255.,c0.a);}
vec4 stJpSharp(ivec2 p){
  ivec2 mx=u_full-1;vec4 c0=texelFetch(u_tex,p,0);vec3 c=c0.rgb*255.,b=vec3(0.);
  for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++)b+=texelFetch(u_tex,clamp(p+ivec2(dx,dy),ivec2(0),mx),0).rgb*255.;
  b/=9.;return vec4(clamp(floor(c+jpSharp*2.*(c-b)+.5),0.,255.)/255.,c0.a);}

void main(){
  ivec2 p=ivec2(gl_FragCoord.xy);   // linha 0 = primeira linha do quadro (sem inverter)
  vec4 c=vec4(0);
  if(u_stage==S_PIXDOWN) {o=stPixDown(p);return;}
  if(u_stage==S_PIXUP)   {o=stPixUp(p);return;}
  if(u_stage==S_NTSC)    {o=stNtsc(p);return;}
  if(u_stage==S_DISTORT) {o=stDistort(p);return;}
  if(u_stage==S_CRT)     {o=stCrt(p);return;}
  if(u_stage==S_TAPE)    {o=stTape(p);return;}
  if(u_stage==12)        {o=stJpeg(p);return;}
  if(u_stage==13)        {o=stJpSharp(p);return;}
  c=F(p);
  if(u_stage==S_COLOR)         o=stColor(c);
  else if(u_stage==S_PALETTE)  o=stPalette(p,c);
  else if(u_stage==S_HALFTONE) o=stHalftone(p,c);
  else if(u_stage==S_SCAN)     o=stScan(p,c);
  else if(u_stage==S_VIG)      o=stVig(p,c);
  else if(u_stage==S_NOISE)    o=stNoise(p,c);
  else o=c;}
