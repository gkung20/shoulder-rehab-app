/* Willy, the rehabilitation guide: procedural three.js model.
   Used only to (re)generate the sprite layers in assets/willy/.
   Parts are tagged with userData.layer: body | head | armL | armR (screen side). */
function buildWilly(THREE, accentHex = 0xf07a22) {
  const M = {
    silver: new THREE.MeshPhysicalMaterial({color:0xd5d9dd, metalness:0.5, roughness:0.3, clearcoat:0.5, clearcoatRoughness:0.2}),
    teal:   new THREE.MeshPhysicalMaterial({color:0x52b9bd, metalness:0.1, roughness:0.35, clearcoat:0.6, clearcoatRoughness:0.15}),
    headT:  new THREE.MeshPhysicalMaterial({color:0x9ad6d8, metalness:0.1, roughness:0.32, clearcoat:0.6, clearcoatRoughness:0.15}),
    accent: new THREE.MeshPhysicalMaterial({color:accentHex, metalness:0, roughness:0.4, clearcoat:0.5, clearcoatRoughness:0.2}),
    dark:   new THREE.MeshStandardMaterial({color:0x23282c, metalness:0.3, roughness:0.45}),
    visor:  new THREE.MeshPhysicalMaterial({color:0x05080a, metalness:0.2, roughness:0.08, clearcoat:1, clearcoatRoughness:0.02}),
    copper: new THREE.MeshStandardMaterial({color:0xb07a4a, metalness:0.9, roughness:0.3}),
    glow:   new THREE.MeshStandardMaterial({color:0x40f0ff, emissive:0x2be6ff, emissiveIntensity:2.2}),
    pupil:  new THREE.MeshStandardMaterial({color:0x0a3c44, emissive:0x0e7f8f, emissiveIntensity:0.7, roughness:0.2}),
    white:  new THREE.MeshStandardMaterial({color:0xffffff, emissive:0xffffff, emissiveIntensity:1.5}),
  };
  Object.values(M).forEach(m => m.envMapIntensity = 0.8);
  const mesh = (geo, mat, parent, pos=[0,0,0], rot=[0,0,0], scl=[1,1,1]) => {
    const m = new THREE.Mesh(geo, mat); m.position.set(...pos); m.rotation.set(...rot); m.scale.set(...scl); parent.add(m); return m;
  };
  const grp = (parent, pos=[0,0,0]) => { const g = new THREE.Group(); g.position.set(...pos); parent.add(g); return g; };
  const S = (r, w=48, h=32, ...a) => new THREE.SphereGeometry(r, w, h, ...a);

  const willy = new THREE.Group();
  const torso = grp(willy, [0, 1.2, 0]);
  const bodyScale = [1, 0.95, 0.92];
  mesh(S(0.78, 64, 48), M.silver, torso, [0,0,0], [0,0,0], bodyScale);
  mesh(S(0.786, 64, 48, Math.PI/2 - 0.85, 1.7, 0.5, 0.95), M.teal, torso, [0,0,0], [0,0,0], bodyScale);
  mesh(S(0.786, 32, 24, -0.55, 0.6, 0.6, 0.8), M.teal, torso, [0,0,0], [0,0,0], bodyScale);
  mesh(S(0.786, 32, 24, Math.PI - 0.05, 0.6, 0.6, 0.8), M.teal, torso, [0,0,0], [0,0,0], bodyScale);
  mesh(new THREE.CapsuleGeometry(0.085, 0.24, 8, 16), M.accent, torso, [0, -0.3, 0.655], [0.4, 0, Math.PI/2], [1, 1, 0.5]);
  const hs = new THREE.Shape();
  hs.moveTo(0, -0.11); hs.bezierCurveTo(-0.02,-0.08,-0.13,-0.02,-0.13,0.04); hs.bezierCurveTo(-0.13,0.11,-0.04,0.13,0,0.07);
  hs.bezierCurveTo(0.04,0.13,0.13,0.11,0.13,0.04); hs.bezierCurveTo(0.13,-0.02,0.02,-0.08,0,-0.11);
  mesh(new THREE.ExtrudeGeometry(hs, {depth:0.04, bevelEnabled:true, bevelThickness:0.015, bevelSize:0.012, bevelSegments:4, curveSegments:24}),
       M.accent, torso, [0, 0.12, 0.675], [-0.12, 0, 0], [1.1, 1.1, 1]);
  mesh(new THREE.CylinderGeometry(0.3, 0.34, 0.2, 40), M.dark, torso, [0, 0.74, 0]);
  mesh(new THREE.TorusGeometry(0.33, 0.045, 16, 48), M.accent, torso, [0, 0.66, 0], [Math.PI/2, 0, 0]);
  [-1, 1].forEach(s => mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.04, 24), M.dark, torso, [s*0.74, -0.18, 0.18], [0, 0, Math.PI/2]));

  const head = grp(torso, [0, 1.38, 0]);
  const HS = [1.12, 0.92, 1];
  mesh(S(0.8, 64, 48), M.headT, head, [0,0,0], [0,0,0], HS);
  mesh(S(0.805, 64, 16, 0, Math.PI*2, 1.95, 0.45), M.silver, head, [0,0,0], [0,0,0], HS);
  function shell(r, a, b, oy) {
    const g = new THREE.SphereGeometry(r, 160, 120).toNonIndexed(), src = g.attributes.position.array, out = [];
    for (let i = 0; i < src.length; i += 9) {
      const cx = (src[i]+src[i+3]+src[i+6])/(3*r), cy = (src[i+1]+src[i+4]+src[i+7])/(3*r) - oy, cz = (src[i+2]+src[i+5]+src[i+8])/(3*r);
      if (cz > 0 && (Math.abs(cx)/a)**4 + (Math.abs(cy)/b)**4 < 1) for (let k = 0; k < 9; k++) out.push(src[i+k]);
    }
    const ng = new THREE.BufferGeometry(); ng.setAttribute('position', new THREE.Float32BufferAttribute(out, 3)); ng.computeVertexNormals();
    return ng;
  }
  mesh(shell(0.818, 0.7, 0.44, -0.04), M.copper, head, [0,0,0], [0,0,0], HS);
  mesh(shell(0.83, 0.66, 0.4, -0.04), M.visor, head, [0,0,0], [0,0,0], HS);
  const onVisor = (ux, uy, lift = 0.006) => {
    const uz = Math.sqrt(1 - ux*ux - uy*uy), r = 0.83;
    const pos = new THREE.Vector3(ux*r*HS[0], uy*r*HS[1], uz*r*HS[2]);
    const n = new THREE.Vector3(pos.x/HS[0]**2, pos.y/HS[1]**2, pos.z/HS[2]**2).normalize();
    return {pos: pos.addScaledVector(n, lift), n};
  };
  const placeOn = (obj, v) => { obj.position.copy(v.pos); obj.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), v.n); };
  const eyes = [];
  [-1, 1].forEach(s => {
    const e = grp(head); placeOn(e, onVisor(s * 0.3, 0.03));
    const open = grp(e);
    mesh(new THREE.TorusGeometry(0.12, 0.028, 16, 48), M.glow, open);
    mesh(new THREE.CircleGeometry(0.095, 40), M.pupil, open, [0, 0, -0.004]);
    mesh(new THREE.TorusGeometry(0.06, 0.01, 8, 32), M.glow, open, [0, 0, 0.002]);
    mesh(new THREE.CircleGeometry(0.022, 16), M.white, open, [0.035, 0.04, 0.006]);
    const happy = grp(e);
    mesh(new THREE.TorusGeometry(0.1, 0.03, 16, 32, Math.PI), M.glow, happy, [0, -0.04, 0]);
    happy.visible = false;
    eyes.push({open, happy});
  });
  const smileG = grp(head); placeOn(smileG, onVisor(0, -0.24));
  const smile = mesh(new THREE.TorusGeometry(0.09, 0.016, 12, 32, Math.PI), M.glow, smileG, [0,0,0], [0, 0, Math.PI]);
  const mouth = mesh(new THREE.CircleGeometry(0.075, 32), M.glow, smileG, [0, 0.02, 0.002]);
  mouth.visible = false;
  [-1, 1].forEach(s => {
    mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.14, 40), M.accent, head, [s*0.86, -0.02, 0], [0, 0, Math.PI/2]);
    mesh(new THREE.CylinderGeometry(0.13, 0.15, 0.08, 40), M.silver, head, [s*0.95, -0.02, 0], [0, 0, Math.PI/2]);
  });
  mesh(new THREE.BoxGeometry(0.2, 0.08, 0.26), M.accent, head, [0, 0.72, 0.05]);
  mesh(new THREE.CylinderGeometry(0.018, 0.025, 0.42, 12), M.silver, head, [0, 0.95, 0]);
  mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.12, 12), M.dark, head, [0, 0.8, 0]);
  mesh(S(0.085, 24, 16), M.silver, head, [0, 1.2, 0]);

  function makeArm(s) {
    const sh = grp(torso, [s*0.8, 0.3, 0]);
    mesh(S(0.22), M.silver, sh, [0, 0.02, 0], [0,0,0], [1, 1, 0.95]);
    mesh(new THREE.TorusGeometry(0.2, 0.035, 12, 40), M.accent, sh, [s*0.06, 0, 0], [0, Math.PI/2, 0]);
    mesh(new THREE.CylinderGeometry(0.075, 0.075, 0.28, 20), M.dark, sh, [0, -0.28, 0]);
    const el = grp(sh, [0, -0.44, 0]);
    mesh(S(0.1, 24, 16), M.dark, el);
    mesh(new THREE.CylinderGeometry(0.15, 0.17, 0.32, 32), M.silver, el, [0, -0.2, 0]);
    mesh(new THREE.TorusGeometry(0.155, 0.03, 12, 40), M.accent, el, [0, -0.05, 0], [Math.PI/2, 0, 0]);
    mesh(new THREE.TorusGeometry(0.172, 0.032, 12, 40), M.accent, el, [0, -0.35, 0], [Math.PI/2, 0, 0]);
    const hand = grp(el, [0, -0.46, 0]);
    mesh(S(0.1, 24, 16), M.dark, hand, [0,0,0], [0,0,0], [1, 0.9, 0.8]);
    const fg = new THREE.CapsuleGeometry(0.034, 0.1, 6, 12);
    [-0.06, 0, 0.06].forEach(z => mesh(fg, M.dark, hand, [s*0.02, -0.12, z], [z*2, 0, s*0.15]));
    mesh(fg, M.dark, hand, [-s*0.08, -0.08, 0.03], [0, 0, -s*0.6]);
    return {sh, el};
  }
  // s=+1 sits at +x, which is the right-hand side of the screen (Willy faces the viewer).
  const arms = {R: makeArm(1), L: makeArm(-1)};
  [-1, 1].forEach(s => {
    const leg = grp(willy, [s*0.32, 0, 0]);
    mesh(S(0.14, 24, 16), M.dark, leg, [0, 0.6, 0]);
    mesh(new THREE.CylinderGeometry(0.2, 0.24, 0.38, 36), M.silver, leg, [0, 0.38, 0]);
    mesh(new THREE.TorusGeometry(0.205, 0.035, 12, 40), M.accent, leg, [0, 0.55, 0], [Math.PI/2, 0, 0]);
    mesh(S(0.27, 40, 24, 0, Math.PI*2, 0, Math.PI/2), M.silver, leg, [0, 0.06, 0.08], [0,0,0], [1, 0.75, 1.3]);
    mesh(new THREE.CylinderGeometry(0.28, 0.28, 0.07, 40), M.accent, leg, [0, 0.035, 0.08], [0,0,0], [1, 1, 1.3]);
  });

  const tag = (root, layer) => root.traverse(o => { if (o.isMesh) o.userData.layer = layer; });
  tag(willy, 'body'); tag(head, 'head'); tag(arms.L.sh, 'armL'); tag(arms.R.sh, 'armR');

  // Pose: angle in degrees of lateral elevation (0 = arm down), elbow in degrees.
  function setArm(side, deg, elbowDeg = 0) {
    const s = side === 'R' ? 1 : -1, a = arms[side];
    a.sh.rotation.set(0, 0, s * (deg * Math.PI / 180 + 0.12));
    a.el.rotation.set(-0.15, 0, s * elbowDeg * Math.PI / 180);
  }
  function setFace(eyesState, mouthState) {
    eyes.forEach(e => { e.open.visible = eyesState !== 'happy'; e.happy.visible = eyesState === 'happy'; e.open.scale.y = eyesState === 'blink' ? 0.1 : 1; });
    smile.visible = mouthState === 'smile';
    mouth.visible = mouthState !== 'smile';
    mouth.scale.set(mouthState === 'talk2' ? 1.1 : 0.9, mouthState === 'talk2' ? 0.85 : 0.35, 1);
  }
  return {willy, torso, head, arms, setArm, setFace, neck: new THREE.Vector3(0, 1.2 + 0.7, 0)};
}
if (typeof module !== 'undefined') module.exports = {buildWilly};
