// Original hero loop for the CausalGraph legal agent: holographic contract pages,
// agent light streams that flag and then resolve clauses, depth particles and bloom.
// Every motion is periodic in LOOP seconds, so frame N and frame 0 join seamlessly.
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { ShaderPass } from 'three/addons/postprocessing/ShaderPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

const q = new URLSearchParams(location.search);
const W = +q.get('w') || 1920;
const H = +q.get('h') || 1080;
const PORTRAIT = q.get('mode') === 'portrait';
const LOOP = 12;
const TAU = Math.PI * 2;

function mulberry32(a) {
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(20261001);
const frac = (x) => x - Math.floor(x);
const tmpRail = new THREE.Vector3();
const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };

const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, alpha: false });
renderer.setPixelRatio(1);
renderer.setSize(W, H);
renderer.setClearColor(0x000000, 1);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(PORTRAIT ? 50 : 32, W / H, 0.1, 300);

/* ------------------------------------------------------------------ noise */
const NOISE = /* glsl */`
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec2 mod289(vec2 x){return x-floor(x*(1.0/289.0))*289.0;}
vec3 permute(vec3 x){return mod289(((x*34.0)+1.0)*x);}
float snoise(vec2 v){
  const vec4 C=vec4(0.211324865405187,0.366025403784439,-0.577350269189626,0.024390243902439);
  vec2 i=floor(v+dot(v,C.yy)); vec2 x0=v-i+dot(i,C.xx);
  vec2 i1=(x0.x>x0.y)?vec2(1.0,0.0):vec2(0.0,1.0);
  vec4 x12=x0.xyxy+C.xxzz; x12.xy-=i1; i=mod289(i);
  vec3 p=permute(permute(i.y+vec3(0.0,i1.y,1.0))+i.x+vec3(0.0,i1.x,1.0));
  vec3 m=max(0.5-vec3(dot(x0,x0),dot(x12.xy,x12.xy),dot(x12.zw,x12.zw)),0.0); m=m*m; m=m*m;
  vec3 x=2.0*fract(p*C.www)-1.0; vec3 h=abs(x)-0.5; vec3 ox=floor(x+0.5); vec3 a0=x-ox;
  m*=1.79284291400159-0.85373472095314*(a0*a0+h*h);
  vec3 g; g.x=a0.x*x0.x+h.x*x0.y; g.yz=a0.yz*x12.xz+h.yz*x12.yw;
  return 130.0*dot(m,g);
}
float fbm(vec2 p){float a=0.5,s=0.0;for(int i=0;i<5;i++){s+=a*snoise(p);p=p*2.03+vec2(1.7,9.2);a*=0.5;}return s;}
`;

/* ------------------------------------------------------------- background */
const focus = PORTRAIT ? new THREE.Vector2(0.05, 0.22) : new THREE.Vector2(0.38, 0.14);
const bgMat = new THREE.ShaderMaterial({
  depthTest: false, depthWrite: false,
  uniforms: { uPhase: { value: 0 }, uAspect: { value: W / H }, uFocus: { value: focus } },
  vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position=vec4(position.xy,0.9999,1.0); }',
  fragmentShader: /* glsl */`
    varying vec2 vUv; uniform float uPhase; uniform float uAspect; uniform vec2 uFocus;
    ${NOISE}
    void main(){
      vec2 p=(vUv-0.5)*vec2(uAspect,1.0);
      float th=uPhase*6.2831853;
      vec2 loop=vec2(cos(th),sin(th))*0.42;
      float n=fbm(p*1.35+loop+vec2(3.1,1.7));
      float n2=fbm(p*2.4-loop*0.8+vec2(-2.3,4.1));
      vec2 c=uFocus;
      float g1=exp(-dot(p-c,p-c)*2.0);
      float g2=exp(-dot(p-c-vec2(0.42,-0.28),p-c-vec2(0.42,-0.28))*3.2);
      float g3=exp(-dot(p-c+vec2(0.55,0.05),p-c+vec2(0.55,0.05))*3.6);
      vec3 col=vec3(0.0004,0.0004,0.0012);
      col+=vec3(0.021,0.008,0.060)*g1*(0.55+0.45*n);
      col+=vec3(0.002,0.018,0.046)*g2*(0.45+0.55*n2);
      col+=vec3(0.032,0.003,0.021)*g3*max(n2+0.15,0.0);
      col+=vec3(0.006,0.008,0.022)*exp(-pow((p.y+0.18-0.08*n)*5.0,2.0));
      gl_FragColor=vec4(col,1.0);
    }`,
});
const bg = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), bgMat);
bg.frustumCulled = false; bg.renderOrder = -10;
scene.add(bg);

/* ------------------------------------------------------------------ pages */
const PAGE_W = 2.1, PAGE_H = 2.97;
const ROWS = 24, ROW0 = 0.835, ROW_STEP = 0.0305;
const MAX_EV = 8;
const pageMat = (seed, opacity) => new THREE.ShaderMaterial({
  transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
  uniforms: {
    uSeed: { value: seed }, uOpacity: { value: opacity },
    uRip: { value: Array.from({ length: MAX_EV }, () => new THREE.Vector4()) },
    uHi: { value: Array.from({ length: MAX_EV }, () => new THREE.Vector4()) },
    uPulse: { value: 0 },
  },
  vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
  fragmentShader: /* glsl */`
    varying vec2 vUv;
    uniform float uSeed, uOpacity, uPulse;
    uniform vec4 uRip[${MAX_EV}];
    uniform vec4 uHi[${MAX_EV}];
    const vec2 S=vec2(${PAGE_W.toFixed(2)},${PAGE_H.toFixed(2)});
    float hash(float n){return fract(sin(n)*43758.5453123);}
    float box(vec2 p, vec2 b, float r){vec2 d=abs(p)-b+r;return length(max(d,0.0))+min(max(d.x,d.y),0.0)-r;}
    void main(){
      vec2 uv=vUv;
      vec2 w=(uv-0.5)*S;                       // page-local world units
      float edge=-box(w,S*0.5,0.06);           // >0 inside
      float aa=fwidth(edge)*1.2+1e-4;
      float inside=smoothstep(-aa,aa,edge);
      float rim=exp(-max(edge,0.0)*55.0)*inside + exp(-abs(edge)*140.0)*0.6;
      float t=uv.x*0.55+(1.0-uv.y)*0.45;
      vec3 cyan=vec3(0.20,0.82,1.0), violet=vec3(0.56,0.38,1.0), pink=vec3(1.0,0.32,0.72);
      vec3 rimCol=mix(cyan,violet,smoothstep(0.0,0.6,t));
      rimCol=mix(rimCol,pink,smoothstep(0.55,1.0,t));
      vec3 col=vec3(0.0);
      // glass body: soft sheen from the upper-left corner plus a faint inner gradient
      float sheen=exp(-dot(uv-vec2(0.08,1.0),uv-vec2(0.08,1.0))*3.0);
      col+=vec3(0.35,0.42,0.95)*(0.010+0.035*sheen)*inside;
      col+=rimCol*rim*(0.55+0.6*uPulse);
      // corner ticks
      vec2 cq=abs(w)-(S*0.5-vec2(0.14));
      float tick=step(0.0,cq.x)*step(0.0,cq.y)*exp(-max(edge,0.0)*160.0);
      col+=vec3(0.75,0.85,1.0)*tick*0.9;
      // header: title, subtitle and a seal mark
      float title=1.0-smoothstep(0.0,aa*2.0,box(w-vec2(-0.34,1.20),vec2(0.42,0.035),0.035));
      float sub=1.0-smoothstep(0.0,aa*2.0,box(w-vec2(-0.47,1.08),vec2(0.29,0.018),0.018));
      float seal=exp(-pow((length(w-vec2(0.70,1.14))-0.11)*70.0,2.0));
      col+=vec3(0.88,0.92,1.0)*title*0.42+vec3(0.7,0.78,1.0)*sub*0.22+vec3(0.6,0.5,1.0)*seal*0.45;
      // body rows
      float rowF=(${ROW0.toFixed(4)}-uv.y)/${ROW_STEP.toFixed(4)}+0.5;
      float ri=floor(rowF);
      if(ri>=0.0 && ri<${ROWS}.0){
        float y0=${ROW0.toFixed(4)}-ri*${ROW_STEP.toFixed(4)};
        float k=mod(ri,6.0);
        float isHead=step(k,0.5);
        float h=hash(ri*7.13+uSeed*31.7);
        float x0=0.11+isHead*0.055;
        float len=isHead>0.5?(0.22+0.18*h):(k>4.5?(0.22+0.32*h):(0.70+0.08*h));
        float x1=min(x0+len,0.89);
        float hw=isHead>0.5?0.0125:0.0085;
        vec2 cp=vec2(clamp(uv.x,x0,x1),y0);
        float d=length((uv-cp)*S)-hw;
        float bar=1.0-smoothstep(0.0,0.0065,d);
        float wx=uv.x*S.x*7.5+h*13.0;
        float gap=step(0.84,fract(wx*(0.85+0.4*hash(ri+3.0+uSeed))));
        bar*=1.0-gap*(1.0-isHead);
        // clause number badge
        float badge=(1.0-smoothstep(0.0,0.006,box((uv-vec2(0.115,y0))*S,vec2(0.022,0.022),0.006)))*isHead;
        vec3 ink=vec3(0.82,0.87,1.0)*(isHead>0.5?0.36:0.17);
        col+=ink*bar+vec3(0.55,0.65,1.0)*badge*0.55;
        // flagged then resolved clauses
        for(int i=0;i<${MAX_EV};i++){
          vec4 e=uHi[i];
          if(e.w>0.5 && abs(e.x-ri)<0.5){
            float a=e.y;
            float risk=smoothstep(0.0,0.22,a)*(1.0-smoothstep(1.7,2.3,a));
            float fixd=smoothstep(1.7,2.3,a)*(1.0-smoothstep(4.8,5.9,a));
            float band=1.0-smoothstep(0.0,0.012,box((uv-vec2((x0+x1)*0.5,y0))*S,vec2((x1-x0)*0.5*S.x+0.05,0.034),0.02));
            float glowB=exp(-max(box((uv-vec2((x0+x1)*0.5,y0))*S,vec2((x1-x0)*0.5*S.x+0.05,0.034),0.02),0.0)*28.0);
            vec3 rc=vec3(1.0,0.22,0.48), fc=vec3(0.22,0.88,1.0);
            col+=rc*(band*0.30+glowB*0.20+bar*1.1)*risk;
            col+=fc*(band*0.22+glowB*0.16+bar*0.9)*fixd;
            float dot1=exp(-length((uv-vec2(0.935,y0))*S)*60.0);
            col+=mix(rc,fc,smoothstep(1.7,2.3,a))*dot1*1.6*max(risk,fixd);
            // the resolved line grows a new insertion bar beneath it
            float grow=smoothstep(1.9,3.0,a);
            vec2 ip=vec2(clamp(uv.x,x0,x0+(x1-x0)*grow),y0-0.0135);
            float ins=1.0-smoothstep(0.0,0.004,length((uv-ip)*S)-0.0035);
            col+=fc*ins*fixd*0.9;
          }
        }
      }
      // agent touch: expanding ring and a bright flash
      for(int i=0;i<${MAX_EV};i++){
        vec4 r=uRip[i];
        if(r.w>0.0){
          vec2 d=(uv-r.xy)*S;
          float rad=r.z*1.25;
          float ring=exp(-pow((length(d)-rad)*22.0,2.0))*exp(-r.z*2.2);
          float flash=exp(-length(d)*7.0)*exp(-r.z*4.5);
          col+=mix(vec3(0.55,0.85,1.0),vec3(0.8,0.6,1.0),0.4)*(ring*0.7+flash*1.6)*r.w*inside;
        }
      }
      gl_FragColor=vec4(col*uOpacity,1.0);
    }`,
});

const pages = [];
const PAGE_COUNT = 6;
for (let k = 0; k < PAGE_COUNT; k++) {
  const mat = pageMat(k * 1.37 + 0.2, Math.exp(-0.27 * k));
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(PAGE_W, PAGE_H), mat);
  if (PORTRAIT) {
    mesh.position.set(0.1 + 0.95 * k, 1.2 + 0.32 * k, -2.3 * k);
    mesh.rotation.set(0.05, -0.55 + 0.08 * k, -0.035);
  } else {
    mesh.position.set(1.75 + 1.3 * k, 0.05 + 0.12 * k, -2.3 * k);
    mesh.rotation.set(0.05, -0.62 + 0.09 * k, -0.035);
  }
  mesh.renderOrder = 10 - k;
  mesh.updateMatrixWorld(true);
  scene.add(mesh);
  pages.push({ mesh, mat, inv: mesh.matrixWorld.clone().invert() });
}

/* ---------------------------------------------------------- agent streams */
const STREAMS = [
  { color: [0.62, 0.42, 1.0], cycles: 1, phase: 0.00, wob: [0.9, 1.3, 0.0], seed: 1 },
  { color: [0.22, 0.85, 1.0], cycles: 1, phase: 0.21, wob: [1.2, 0.8, 1.1], seed: 2 },
  { color: [1.0, 0.34, 0.72], cycles: 1, phase: 0.47, wob: [0.7, 1.1, 2.3], seed: 3 },
  { color: [0.38, 0.58, 1.0], cycles: 1, phase: 0.66, wob: [1.4, 0.6, 3.1], seed: 4 },
  { color: [0.85, 0.82, 1.0], cycles: 1, phase: 0.86, wob: [1.0, 1.0, 4.4], seed: 5 },
];
// The agent streams are born in the AI core behind the stack, pierce chosen pages at
// chosen clauses (page-local x, y), and leave the frame past the camera.
const CORE = PORTRAIT ? new THREE.Vector3(2.4, 9.4, -19) : new THREE.Vector3(8.2, 5.7, -22);
const CORE_R = 2.0;
const ROUTES = [
  { dir: [-0.3, -0.8, 0.5], hits: [[5, -0.4, 0.62], [3, 0.3, 0.05], [1, -0.2, -0.55], [0, 0.35, 0.2]], to: PORTRAIT ? [-4, -7, 7] : [2.5, -7, 7] },
  { dir: [-0.7, -0.4, 0.6], hits: [[4, 0.4, -0.7], [2, -0.35, 0.68], [0, -0.3, -0.42]], to: PORTRAIT ? [-5, 8, 6] : [1.5, 7, 6] },
  { dir: [0.4, -0.6, 0.6], hits: [[5, 0.3, -0.2], [2, 0.2, -0.95], [1, -0.4, 0.86]], to: PORTRAIT ? [5, 9, 6] : [6.5, 6, 6] },
  { dir: [0.1, -0.9, 0.4], hits: [[4, -0.3, 0.33], [3, 0.4, -0.85], [0, 0.1, 0.78]], to: PORTRAIT ? [4, -8, 6] : [3, -6.5, 6] },
  { dir: [-0.8, -0.2, 0.5], hits: [[5, 0.0, -0.9], [3, -0.45, 0.66], [1, 0.3, 0.3]], to: PORTRAIT ? [-6, 1.5, 4] : [-0.5, -7.5, 6] },
];
STREAMS.forEach((s, si) => {
  const route = ROUTES[si];
  const dir = new THREE.Vector3(...route.dir).normalize();
  const pts = [CORE.clone().addScaledVector(dir, CORE_R * 0.6), CORE.clone().addScaledVector(dir, CORE_R * 1.9)];
  route.hits.forEach(([pi, x, y]) => pts.push(new THREE.Vector3(x, y, 0).applyMatrix4(pages[pi].mesh.matrixWorld)));
  pts.push(new THREE.Vector3(...route.to));
  s.curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal');
  s.samples = s.curve.getSpacedPoints(6000);
});

// Where each stream pierces each page, in curve parameter and page uv.
const crossings = [];
STREAMS.forEach((s, si) => {
  pages.forEach((pg, pi) => {
    let prev = null;
    s.samples.forEach((pt, j) => {
      const local = pt.clone().applyMatrix4(pg.inv);
      if (prev && Math.sign(prev.z) !== Math.sign(local.z)) {
        const t = prev.z / (prev.z - local.z);
        const x = prev.x + (local.x - prev.x) * t, y = prev.y + (local.y - prev.y) * t;
        if (Math.abs(x) < PAGE_W * 0.47 && Math.abs(y) < PAGE_H * 0.47) {
          const u = x / PAGE_W + 0.5, v = y / PAGE_H + 0.5;
          const row = Math.round((ROW0 - v) / ROW_STEP);
          crossings.push({ si, pi, param: (j - 1 + t) / (s.samples.length - 1), u, v, row: row >= 0 && row < ROWS ? row : -1, at: pt.clone(), n: new THREE.Vector3(0, 0, 1).transformDirection(pg.mesh.matrixWorld) });
        }
      }
      prev = local;
    });
  });
});
window.__crossings = crossings.map((c) => [c.si, c.pi, +c.param.toFixed(3), c.row]);

const TRAIL = 340, TRAIL_LEN = 0.2;
const pointsVS = /* glsl */`
  attribute float aSize; attribute vec4 aColor; varying vec4 vColor; uniform float uScale; uniform float uFocusZ;
  void main(){
    vec4 mv=modelViewMatrix*vec4(position,1.0);
    float coc=abs(-mv.z-uFocusZ);
    float blur=clamp(coc*0.09,0.0,4.0);
    gl_PointSize=aSize*uScale*(1.0+blur*1.6)/max(-mv.z,0.1);
    vColor=vec4(aColor.rgb,aColor.a/(1.0+blur*blur*1.8));
    gl_Position=projectionMatrix*mv;
  }`;
const pointsFS = /* glsl */`
  varying vec4 vColor; uniform float uSoft;
  void main(){
    vec2 d=gl_PointCoord-0.5; float r=length(d)*2.0;
    float core=exp(-r*r*uSoft);
    float disc=smoothstep(1.0,0.82,r);
    float a=mix(core,disc*0.9,step(uSoft,0.0));
    gl_FragColor=vec4(vColor.rgb*vColor.a*a,1.0);
  }`;
function makePoints(count, soft) {
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3));
  geo.setAttribute('aSize', new THREE.BufferAttribute(new Float32Array(count), 1));
  geo.setAttribute('aColor', new THREE.BufferAttribute(new Float32Array(count * 4), 4));
  const mat = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending,
    uniforms: { uScale: { value: H / 1080 * 10 }, uFocusZ: { value: 10.5 }, uSoft: { value: soft } },
    vertexShader: pointsVS, fragmentShader: pointsFS,
  });
  const pts = new THREE.Points(geo, mat);
  pts.frustumCulled = false;
  scene.add(pts);
  return pts;
}

const trails = makePoints(STREAMS.length * TRAIL, 4.5);
trails.renderOrder = 20;
const heads = makePoints(STREAMS.length * 2, 5.0);
heads.renderOrder = 21;

const SPARKS = 900;
const sparks = makePoints(STREAMS.length * SPARKS, 5.0);
sparks.renderOrder = 19;
const sparkData = STREAMS.map((s) => Array.from({ length: SPARKS }, () => ({
  b: rand(), life: 0.9 + rand() * 2.0,
  v: new THREE.Vector3(rand() - 0.5, rand() - 0.5, rand() - 0.5).normalize().multiplyScalar(0.18 + rand() * 0.55),
  size: 0.8 + rand() * 2.2, tint: rand(),
})));

/* ---------------------------------------------------------------- AI core */
const RINGS = 46, PER_RING = 260;
const CORE_N = RINGS * PER_RING + 2400;
const core = makePoints(CORE_N, 4.0);
core.renderOrder = 3;
const coreData = [];
for (let r = 0; r < RINGS; r++) {
  const lat = -Math.PI / 2 + (r + 0.5) / RINGS * Math.PI;
  const count = Math.max(24, Math.round(PER_RING * Math.cos(lat)));
  const spin = [1, -1, 2, -1, 1][r % 5];
  for (let j = 0; j < count; j++) coreData.push({ ring: true, lat, lon: j / count * TAU + rand() * 0.02, spin, n: rand(), size: rand() < 0.02 ? 12 : 3.6 + rand() * 2.8 });
}
for (let i = 0; i < 2400; i++) {
  const y = 1 - (i + 0.5) / 2400 * 2, rr = Math.sqrt(1 - y * y), phi = i * 2.399963229728653;
  coreData.push({ ring: false, d: new THREE.Vector3(Math.cos(phi) * rr, y, Math.sin(phi) * rr), shell: 0.25 + rand() * 0.55, n: rand(), size: 3 + rand() * 4 });
}
const coreGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: null, color: 0xffffff, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false, transparent: true }));
// rails: the faint full path of every stream, like a long exposure
const RAIL = 700;
const rails = makePoints(STREAMS.length * RAIL, 3.0);
rails.renderOrder = 18;
STREAMS.forEach((s, si) => {
  const rp = rails.geometry.attributes.position.array, rs = rails.geometry.attributes.aSize.array, rc = rails.geometry.attributes.aColor.array;
  for (let j = 0; j < RAIL; j++) {
    s.curve.getPointAt(j / (RAIL - 1), tmpRail);
    const i = si * RAIL + j;
    rp.set([tmpRail.x, tmpRail.y, tmpRail.z], i * 3);
    rs[i] = 1.3;
    const fade = smooth(0.0, 0.08, j / RAIL) * (1 - smooth(0.85, 1.0, j / RAIL));
    rc.set([s.color[0], s.color[1], s.color[2], 0.11 * fade], i * 4);
  }
});
// bursts where a stream pierces a page
const BURST = 46;
const bursts = makePoints(BURST * 64, 5.0);
bursts.renderOrder = 22;
// anamorphic streaks on every stream head
const streakTex = (() => {
  const c = document.createElement('canvas'); c.width = 512; c.height = 32;
  const g = c.getContext('2d');
  const grd = g.createLinearGradient(0, 0, 512, 0);
  grd.addColorStop(0, 'rgba(255,255,255,0)'); grd.addColorStop(0.5, 'rgba(255,255,255,1)'); grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd; g.fillRect(0, 0, 512, 32);
  const v = g.createLinearGradient(0, 0, 0, 32);
  v.addColorStop(0, 'rgba(0,0,0,1)'); v.addColorStop(0.5, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,1)');
  g.globalCompositeOperation = 'destination-out'; g.fillStyle = v; g.fillRect(0, 0, 512, 32);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
})();
const streaks = STREAMS.map((s) => {
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: streakTex, color: new THREE.Color(...s.color), blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false, transparent: true, opacity: 0.55 }));
  sp.renderOrder = 23; scene.add(sp); return sp;
});

/* -------------------------------------------------------------- dust field */
const DUST = 16000;
const dust = makePoints(DUST, 3.0);
dust.renderOrder = 5;
const dustData = Array.from({ length: DUST }, () => {
  const z = -32 + rand() * 40;
  const spread = 1.0 + (8 - z) * 0.07;
  return {
    base: new THREE.Vector3((rand() - 0.5) * 22 * spread, (rand() - 0.5) * 12 * spread, z),
    amp: 0.1 + rand() * 0.45, ph: [rand() * TAU, rand() * TAU, rand() * TAU], k: 1 + Math.floor(rand() * 2),
    size: rand() < 0.04 ? 3 + rand() * 6 : 0.6 + rand() * 1.6,
    col: rand() < 0.15 ? [0.7, 0.5, 1.0] : rand() < 0.3 ? [0.4, 0.85, 1.0] : [0.75, 0.82, 1.0],
    a: 0.12 + rand() * 0.5,
  };
});

/* ------------------------------------------------------- backlight + rays */
const glowTex = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 256;
  const g = c.getContext('2d');
  const grd = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.25, 'rgba(255,255,255,0.35)');
  grd.addColorStop(0.6, 'rgba(255,255,255,0.06)'); grd.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grd; g.fillRect(0, 0, 256, 256);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
})();
coreGlow.material.map = glowTex; coreGlow.material.color = new THREE.Color(0.5, 0.36, 1.0); coreGlow.material.opacity = 0.16;
coreGlow.position.copy(CORE); coreGlow.scale.setScalar(CORE_R * 4.2); coreGlow.renderOrder = 2; scene.add(coreGlow);
const coreHot = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: new THREE.Color(0.85, 0.8, 1.0), blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false, transparent: true, opacity: 0.5 }));
coreHot.position.copy(CORE); coreHot.scale.setScalar(CORE_R * 1.6); coreHot.renderOrder = 4; scene.add(coreHot);
const back = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: new THREE.Color(0.42, 0.3, 1.0), blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false, transparent: true, opacity: 0.07 }));
back.position.copy(pages[3].mesh.position).add(new THREE.Vector3(0.6, 0.4, -2.5));
back.scale.setScalar(PORTRAIT ? 8 : 9);
back.renderOrder = 1;
scene.add(back);
const back2 = back.clone(); back2.material = back.material.clone();
back2.material.color = new THREE.Color(0.12, 0.55, 1.0); back2.material.opacity = 0.08;
back2.position.add(new THREE.Vector3(2.2, -1.6, -3)); back2.scale.setScalar(PORTRAIT ? 9 : 11);
scene.add(back2);

const rayMat = new THREE.ShaderMaterial({
  transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
  uniforms: { uPhase: { value: 0 }, uSeed: { value: 0 } },
  vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
  fragmentShader: /* glsl */`varying vec2 vUv; uniform float uPhase, uSeed;
    void main(){
      float across=exp(-pow((vUv.x-0.5)*3.2,2.0));
      float along=smoothstep(0.0,0.35,vUv.y)*smoothstep(1.0,0.55,vUv.y);
      float flick=0.75+0.25*sin(6.2831853*uPhase+uSeed*4.0);
      gl_FragColor=vec4(vec3(0.42,0.36,1.0)*across*along*0.022*flick,1.0);
    }`,
});
const rays = [];
for (let i = 0; i < 5; i++) {
  const m = rayMat.clone();
  m.uniforms.uSeed.value = i * 1.7;
  const ray = new THREE.Mesh(new THREE.PlaneGeometry(1.3 + i * 0.35, 26), m);
  ray.position.set((PORTRAIT ? 2.5 : 5.5) + i * 0.9, 5 + i * 0.3, -9 - i * 1.6);
  ray.rotation.set(0, 0, 0.62 + i * 0.07);
  ray.renderOrder = 2;
  scene.add(ray);
  rays.push(ray);
}

/* ------------------------------------------------------------ post stack */
const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(W, H, { type: THREE.HalfFloatType, samples: 4 }));
composer.setPixelRatio(1);
composer.setSize(W, H);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(W, H), 0.9, 0.55, 0.3);
composer.addPass(bloom);
const lens = new ShaderPass({
  uniforms: { tDiffuse: { value: null }, uAspect: { value: W / H } },
  vertexShader: 'varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }',
  fragmentShader: /* glsl */`varying vec2 vUv; uniform sampler2D tDiffuse; uniform float uAspect;
    void main(){
      vec2 c=vUv-0.5; float r2=dot(c*vec2(uAspect,1.0),c*vec2(uAspect,1.0));
      vec2 off=c*0.0045*(0.4+r2);
      vec3 col=vec3(texture2D(tDiffuse,vUv+off).r,texture2D(tDiffuse,vUv).g,texture2D(tDiffuse,vUv-off).b);
      col*=1.0-smoothstep(0.25,1.25,r2)*0.6;
      gl_FragColor=vec4(col,1.0);
    }`,
});
composer.addPass(lens);
composer.addPass(new OutputPass());

/* ------------------------------------------------------------- per frame */
const tmp = new THREE.Vector3();
const camTarget = new THREE.Vector3();
function setTime(seconds) {
  const ph = frac(seconds / LOOP);
  const th = ph * TAU;
  bgMat.uniforms.uPhase.value = ph;
  rays.forEach((r) => { r.material.uniforms.uPhase.value = ph; });

  if (PORTRAIT) {
    camera.position.set(0.35 * Math.sin(th), 0.6 + 0.18 * Math.sin(2 * th), 11.5 - 0.5 * (1 - Math.cos(th)));
    camTarget.set(1.15 + 0.2 * Math.sin(th + 0.6), 0.25 + 0.1 * Math.cos(th), -2.2);
  } else {
    camera.position.set(0.55 * Math.sin(th), 0.3 + 0.2 * Math.sin(2 * th), 10.5 - 0.6 * (1 - Math.cos(th)));
    camTarget.set(0.45 + 0.25 * Math.sin(th + 0.6), 0.12 + 0.08 * Math.cos(th), -1.8);
  }
  camera.lookAt(camTarget);
  camera.rotation.z += 0.012 * Math.sin(th);
  camera.updateMatrixWorld();

  // streams
  const tp = trails.geometry.attributes.position.array, ts = trails.geometry.attributes.aSize.array, tc = trails.geometry.attributes.aColor.array;
  const hp = heads.geometry.attributes.position.array, hs = heads.geometry.attributes.aSize.array, hc = heads.geometry.attributes.aColor.array;
  const sp = sparks.geometry.attributes.position.array, ss = sparks.geometry.attributes.aSize.array, sc = sparks.geometry.attributes.aColor.array;
  STREAMS.forEach((s, si) => {
    const head = frac(ph * s.cycles + s.phase);
    s.head = head;
    for (let j = 0; j < TRAIL; j++) {
      const f = j / (TRAIL - 1);
      const u = frac(head - f * TRAIL_LEN);
      s.curve.getPointAt(u, tmp);
      const i = si * TRAIL + j;
      tp.set([tmp.x, tmp.y, tmp.z], i * 3);
      const taper = Math.pow(1 - f, 1.6);
      ts[i] = 1.4 + 13 * taper;
      const c = s.color;
      const hot = Math.pow(1 - f, 6);
      tc.set([c[0] + hot * 0.6, c[1] + hot * 0.6, c[2] + hot * 0.6, 0.18 + 0.82 * taper], i * 4);
    }
    s.curve.getPointAt(head, tmp);
    hp.set([tmp.x, tmp.y, tmp.z, tmp.x, tmp.y, tmp.z], si * 6);
    hs[si * 2] = 34; hs[si * 2 + 1] = 9;
    hc.set([s.color[0] * 0.5, s.color[1] * 0.5, s.color[2] * 0.5, 0.55, 1.6, 1.6, 1.7, 1.0], si * 8);
    sparkData[si].forEach((d, j) => {
      const age = frac(head - d.b) * LOOP / s.cycles;
      const i = si * SPARKS + j;
      if (age > d.life) { ss[i] = 0; tc; sc[i * 4 + 3] = 0; return; }
      s.curve.getPointAt(d.b, tmp);
      tmp.addScaledVector(d.v, age);
      tmp.y += 0.05 * age * age;
      sp.set([tmp.x, tmp.y, tmp.z], i * 3);
      const life = 1 - age / d.life;
      ss[i] = d.size * (0.5 + 0.5 * life);
      const c = s.color;
      sc.set([c[0] * (0.7 + 0.5 * d.tint), c[1], c[2], life * life * 0.9], i * 4);
    });
  });
  for (const g of [trails, heads, sparks]) {
    g.geometry.attributes.position.needsUpdate = true;
    g.geometry.attributes.aSize.needsUpdate = true;
    g.geometry.attributes.aColor.needsUpdate = true;
  }

  // ripples and clause highlights
  pages.forEach((pg) => {
    pg.mat.uniforms.uRip.value.forEach((v) => v.set(0, 0, 0, 0));
    pg.mat.uniforms.uHi.value.forEach((v) => v.set(-1, 0, 0, 0));
    pg.pulse = 0; pg.nr = 0; pg.nh = 0;
  });
  for (const c of crossings) {
    const s = STREAMS[c.si];
    const age = frac(s.head - c.param) * LOOP / s.cycles;
    const pg = pages[c.pi];
    if (age < 3 && pg.nr < MAX_EV) pg.mat.uniforms.uRip.value[pg.nr++].set(c.u, c.v, age, 1);
    if (c.row >= 0 && age < 6.2 && pg.nh < MAX_EV) pg.mat.uniforms.uHi.value[pg.nh++].set(c.row, age, 0, 1);
    pg.pulse = Math.max(pg.pulse, Math.exp(-age * 2.5));
  }
  pages.forEach((pg) => { pg.mat.uniforms.uPulse.value = pg.pulse; });

  // dust drifts on closed loops
  const dp = dust.geometry.attributes.position.array, ds = dust.geometry.attributes.aSize.array, dc = dust.geometry.attributes.aColor.array;
  dustData.forEach((d, i) => {
    dp[i * 3] = d.base.x + Math.sin(th * d.k + d.ph[0]) * d.amp;
    dp[i * 3 + 1] = d.base.y + Math.sin(th * d.k + d.ph[1]) * d.amp * 0.8 + Math.sin(th + d.ph[2]) * 0.15;
    dp[i * 3 + 2] = d.base.z + Math.cos(th * d.k + d.ph[2]) * d.amp;
    ds[i] = d.size;
    const tw = 0.75 + 0.25 * Math.sin(th * 3 + d.ph[0] * 5);
    dc.set([d.col[0], d.col[1], d.col[2], d.a * tw], i * 4);
  });
  dust.geometry.attributes.position.needsUpdate = true;
  dust.geometry.attributes.aSize.needsUpdate = true;
  dust.geometry.attributes.aColor.needsUpdate = true;


  // AI core: a breathing particle sphere that turns once per loop
  const cp = core.geometry.attributes.position.array, cs = core.geometry.attributes.aSize.array, cc = core.geometry.attributes.aColor.array;
  const ca = Math.cos(th), sa = Math.sin(th);
  coreData.forEach((d, i) => {
    let x, y, z, alpha, cr, cg;
    if (d.ring) {
      const lon = d.lon + th * d.spin;
      const wave = 1 + 0.018 * Math.sin(d.lat * 9 - th * 2) + 0.012 * Math.sin(lon * 3 + th);
      const r = CORE_R * wave;
      x = Math.cos(d.lat) * Math.cos(lon) * r; y = Math.sin(d.lat) * r; z = Math.cos(d.lat) * Math.sin(lon) * r;
      const m = 0.5 + 0.5 * Math.sin(d.lat);
      cr = 0.25 + 0.75 * m; cg = 0.75 - 0.4 * m;
      alpha = 0.2 + 0.55 * Math.pow(Math.max(0, Math.sin(d.lat * 5 - th * 2)), 3);
    } else {
      const r = CORE_R * d.shell * (1 + 0.08 * Math.sin(th * 2 + d.n * 9));
      const c = Math.cos(th), sn = Math.sin(th);
      x = (d.d.x * c - d.d.z * sn) * r; y = d.d.y * r; z = (d.d.x * sn + d.d.z * c) * r;
      cr = 0.75; cg = 0.6; alpha = 0.22 + 0.12 * Math.sin(th * 3 + d.n * 7);
    }
    cp[i * 3] = CORE.x + x; cp[i * 3 + 1] = CORE.y + y; cp[i * 3 + 2] = CORE.z + z;
    cs[i] = d.size;
    cc.set([cr, cg, 1.0, alpha], i * 4);
  });
  core.geometry.attributes.position.needsUpdate = true;
  core.geometry.attributes.aSize.needsUpdate = true;
  core.geometry.attributes.aColor.needsUpdate = true;
  coreGlow.material.opacity = 0.22 + 0.04 * Math.sin(th * 2);
  coreHot.material.opacity = 0.42 + 0.12 * Math.sin(th * 4);

  // bursts from every page crossing, and streaks on the heads
  const bp = bursts.geometry.attributes.position.array, bs = bursts.geometry.attributes.aSize.array, bc = bursts.geometry.attributes.aColor.array;
  bs.fill(0);
  crossings.forEach((c, ci) => {
    if (ci >= 64) return;
    const st = STREAMS[c.si];
    const age = frac(st.head - c.param) * LOOP / st.cycles;
    if (age > 1.6) return;
    const rr = mulberry32(ci * 131 + 7);
    for (let k = 0; k < BURST; k++) {
      const i = ci * BURST + k;
      const life = 0.6 + rr() * 1.0;
      const dirv = new THREE.Vector3(rr() - 0.5, rr() - 0.5, rr() - 0.5).normalize();
      const spd = 0.6 + rr() * 1.6;
      if (age > life) continue;
      const tt = age * (1 - 0.35 * age / life);
      bp.set([c.at.x + (dirv.x + c.n.x * 0.6) * spd * tt, c.at.y + (dirv.y + c.n.y * 0.6) * spd * tt, c.at.z + (dirv.z + c.n.z * 0.6) * spd * tt], i * 3);
      const l = 1 - age / life;
      bs[i] = 1.0 + rr() * 2.2;
      bc.set([st.color[0] + 0.3, st.color[1] + 0.3, st.color[2] + 0.2, l * l * 1.2], i * 4);
    }
  });
  bursts.geometry.attributes.position.needsUpdate = true;
  bursts.geometry.attributes.aSize.needsUpdate = true;
  bursts.geometry.attributes.aColor.needsUpdate = true;
  STREAMS.forEach((st, si) => {
    st.curve.getPointAt(st.head, tmp);
    const sp = streaks[si];
    sp.position.copy(tmp);
    const dist = tmp.distanceTo(camera.position);
    sp.scale.set(0.2 * dist, 0.008 * dist, 1);
    const edge = smooth(0.0, 0.05, st.head) * (1 - smooth(0.93, 1.0, st.head));
    sp.material.opacity = 0.5 * edge * smooth(6, 11, dist);
  });
  back.material.opacity = 0.06 + 0.012 * Math.sin(th);
  back2.material.opacity = 0.07 + 0.015 * Math.sin(th + 2);
}

window.__render = (frame, fps) => {
  setTime(frame / fps);
  composer.render();
  return true;
};
window.__grab = () => {
  const gl = renderer.getContext();
  const px = new Uint8Array(W * H * 4);
  gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, px);
  return px;
};
window.__ready = true;
