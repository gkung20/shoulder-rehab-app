"""Render the 3D guide silhouette frames (assets/silhouette/) from a full-body OBJ.

The OBJ (body-1/Male-low.OBJ, A-pose, Y up, centimetres, facing +Z) is not
stored in the repository: only the rendered frames are. Each frame shows the
body facing the patient with the screen-right arm raised to one angle
(0-160 deg, every 5 deg) like a well-performed lateral raise: in the scapular
plane, elbow soft, shoulder blade rotating with a 2:1 scapulohumeral rhythm
after 30 deg and no shrug. The app flips the frames for the left side. Pixels hold
channels the app recolours at runtime:
    R = diffuse shading, G = fresnel rim, B = unused, A = coverage.

    python -m pip install playwright && python -m playwright install chromium
    python tools/silhouette_frames/render_frames.py C:/Users/you/Desktop/body-1/Male-low.OBJ
"""
import argparse
import base64
import io
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "assets" / "silhouette"
CDN = "https://cdn.jsdelivr.net/npm/three@0.147.0/build/three.min.js"
JOINT = (21.5, 141.0, -7.0)     # glenohumeral joint (+x side), cm
ELBOW = (34.5, 112.0, -9.0)     # elbow joint in the A-pose (+x side)
STERNO = (3.0, 150.0, 2.0)      # sternoclavicular pivot of the shoulder girdle (+x side)
REST_DEG = 22.0                 # arm abduction of the A-pose
OTHER_ARM_DEG = 8               # the arm that is not exercising hangs relaxed
SCAPULAR_PLANE_DEG = 25.0       # lateral raise in the scapular plane, 20-30 deg in front of the body
ELBOW_BEND_DEG = 14.0           # "soft" elbow, constant through the raise
# Scapulohumeral rhythm: ~pure glenohumeral motion for the first 30 deg, then about 2:1
# (glenohumeral : scapular upward rotation). The girdle's visible lift is a fraction of that
# upward rotation, kept small: a good lateral raise keeps the shoulders down (no shrug).
GIRDLE_LIFT_PER_SCAPULAR_DEG = .30
ANGLES = list(range(0, 165, 5))
VIEW = (-52.0, 100.0, -4.0, 226.0)   # x0, x1, y0, y1 in cm: room for the raised arm
PX_PER_CM = 3.0


def load_obj(path):
    vertices, faces = [], []
    for line in Path(path).read_text(errors="ignore").splitlines():
        if line.startswith("v "):
            vertices.append([float(t) for t in line.split()[1:4]])
        elif line.startswith("f "):
            idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
            faces += [[idx[0], idx[k], idx[k + 1]] for k in range(1, len(idx) - 1)]
    return np.asarray(vertices, np.float32), np.asarray(faces, np.int32)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def skin_weights(v):
    """Per-vertex weights: arm (follows the humerus), forearm (follows the elbow), girdle (shoulder blade)."""
    x, y = np.abs(v[:, 0]), v[:, 1]
    joint = np.array(JOINT[:2], np.float32)
    # Around the armpit, decide by direction from the shoulder joint: the arm hangs outward,
    # the side of the chest sits inward. This keeps a clean split and avoids a dragged skin flap.
    direction = np.degrees(np.arctan2(x - joint[0], joint[1] - y))   # 0 = straight down, + = outward
    armpit = smoothstep(-7., 3., direction)
    thighs = smoothstep(25., 31., x)                                  # lower: clear of the thighs
    # Deltoid cap follows the humerus; the upper trapezius only follows the shoulder blade (girdle).
    shoulder = smoothstep(15., 30., x) * (1 - smoothstep(146., 158., y) * (1 - smoothstep(20., 30., x)))
    low, high = smoothstep(100., 110., y), smoothstep(128., 138., y)
    arm = thighs * (1 - low) + armpit * low
    arm = arm * (1 - high) + shoulder * high
    arm *= 1 - smoothstep(158., 166., y)     # never the head or neck
    arm *= smoothstep(66., 72., y)           # never the legs or feet (fingertips end near 78 cm)
    # Forearm: distance along the A-pose upper arm, past the elbow.
    rest = np.radians(REST_DEG)
    along = (x - joint[0]) * np.sin(rest) + (joint[1] - y) * np.cos(rest)
    forearm = arm * smoothstep(28., 35., along)
    # Shoulder girdle: deltoid, upper trapezius and the top of the chest/back move with the scapula.
    girdle = smoothstep(4., 22., x) * smoothstep(118., 136., y) * (1 - smoothstep(150., 172., y))
    girdle = np.maximum(girdle, arm)
    return [w.astype(np.float32) for w in (arm, forearm, girdle)]


def shoulder_angles(elevation, rest=REST_DEG):
    """Split a humerothoracic elevation into girdle lift and glenohumeral rotation (degrees)."""
    scapular = max(0., elevation - 30.) / 3.          # 2:1 after the 30 deg setting phase
    girdle = GIRDLE_LIFT_PER_SCAPULAR_DEG * scapular
    return girdle, elevation - girdle - rest


SETUP = """
window.setupBody = (data, W, H, view) => {
  const canvas = document.createElement('canvas'); canvas.width = W; canvas.height = H; document.body.appendChild(canvas);
  const r = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true, preserveDrawingBuffer: true});
  r.setPixelRatio(1); r.setSize(W, H, false); r.setClearColor(0x000000, 0);
  const cam = new THREE.OrthographicCamera(view[0], view[1], view[3], view[2], -500, 500);
  cam.position.set(0, 0, 200); cam.lookAt(0, 0, 0);
  const base = new Float32Array(data.positions);
  const wArm = new Float32Array(data.arm), wFore = new Float32Array(data.forearm), wGirdle = new Float32Array(data.girdle);
  const geo = new THREE.BufferGeometry();
  const pos = new THREE.BufferAttribute(new Float32Array(base), 3);
  geo.setAttribute('position', pos); geo.setIndex(data.indices);
  const mat = new THREE.ShaderMaterial({
    vertexShader: `varying vec3 vN; varying vec3 vV;
      void main(){ vec4 mv = modelViewMatrix*vec4(position,1.); vN = normalize(normalMatrix*normal); vV = normalize(-mv.xyz);
                   gl_Position = projectionMatrix*mv; }`,
    fragmentShader: `varying vec3 vN; varying vec3 vV;
      void main(){ vec3 n = normalize(vN); if (!gl_FrontFacing) n = -n;
        vec3 L = normalize(vec3(.35,.55,.75));
        float diff = clamp(.35 + .65*max(dot(n,L),0.), 0., 1.);
        float rim = pow(1. - abs(dot(n, normalize(vV))), 2.2);
        gl_FragColor = vec4(diff, rim, 0., 1.); }`,
  });
  const scene = new THREE.Scene(); scene.add(new THREE.Mesh(geo, mat));
  // Rodrigues rotation of v (array of 3) about unit axis k by angle a, around pivot c.
  const rot = (v, k, a, c) => {
    if (Math.abs(a) < 1e-6) return v;
    const x = v[0]-c[0], y = v[1]-c[1], z = v[2]-c[2], cs = Math.cos(a), sn = Math.sin(a);
    const d = k[0]*x + k[1]*y + k[2]*z;
    const cx = k[1]*z - k[2]*y, cy = k[2]*x - k[0]*z, cz = k[0]*y - k[1]*x;
    return [c[0] + x*cs + cx*sn + k[0]*d*(1-cs), c[1] + y*cs + cy*sn + k[1]*d*(1-cs), c[2] + z*cs + cz*sn + k[2]*d*(1-cs)];
  };
  const D = Math.PI / 180, rest = data.rest * D, phi = data.plane * D;
  window.renderAngle = (deg, otherDeg) => {
    const pose = {1: data.angles[deg], [-1]: data.angles[otherDeg]};
    for (let i = 0; i < wArm.length; i++) {
      let v = [base[3*i], base[3*i+1], base[3*i+2]];
      const side = v[0] >= 0 ? 1 : -1, [girdle, gh] = pose[side];
      const J = [side*data.joint[0], data.joint[1], data.joint[2]];
      const E = [side*data.elbow[0], data.elbow[1], data.elbow[2]];
      const S = [side*data.sterno[0], data.sterno[1], data.sterno[2]];
      // 1. soft elbow: forearm swings slightly forward (+z) about the elbow
      if (wFore[i] > 0) v = rot(v, [-Math.cos(rest), -side*Math.sin(rest), 0], data.bend * D * wFore[i], E);
      // 2. glenohumeral elevation in the scapular plane (axis tilted so the arm travels forward of the body)
      if (wArm[i] > 0) v = rot(v, [-Math.sin(phi), 0, side*Math.cos(phi)], gh * D * wArm[i], J);
      // 3. shoulder girdle: small upward rotation about the sternoclavicular joint
      if (wGirdle[i] > 0) v = rot(v, [0, 0, side], girdle * D * wGirdle[i], S);
      pos.array[3*i] = v[0]; pos.array[3*i+1] = v[1]; pos.array[3*i+2] = v[2];
    }
    pos.needsUpdate = true; geo.computeVertexNormals();
    r.render(scene, cam);
    return canvas.toDataURL('image/png');
  };
};
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("obj", type=Path)
    parser.add_argument("--three", help="Local three.min.js (r147) instead of jsDelivr")
    parser.add_argument("--browser", help="Chrome/Chromium executable")
    args = parser.parse_args()
    from PIL import Image
    from playwright.sync_api import sync_playwright
    vertices, faces = load_obj(args.obj)
    arm, forearm, girdle = skin_weights(vertices)
    poses = sorted(set(ANGLES) | {OTHER_ARM_DEG})
    data = {"positions": vertices.ravel().tolist(), "indices": faces.ravel().tolist(),
            "arm": arm.tolist(), "forearm": forearm.tolist(), "girdle": girdle.tolist(),
            "joint": JOINT, "elbow": ELBOW, "sterno": STERNO, "rest": REST_DEG,
            "plane": SCAPULAR_PLANE_DEG, "bend": ELBOW_BEND_DEG,
            "angles": {str(a): shoulder_angles(a) for a in poses}}
    x0, x1, y0, y1 = VIEW
    width, height = round((x1 - x0) * PX_PER_CM), round((y1 - y0) * PX_PER_CM)
    to_px = lambda x, y: [(x - x0) * PX_PER_CM, (y1 - y) * PX_PER_CM]
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("arm_*.png"):
        old.unlink()
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.browser, args=["--use-gl=swiftshader", "--ignore-gpu-blocklist"])
        page = browser.new_page()
        page.set_content("<html><body style='margin:0;background:transparent'></body></html>")
        page.add_script_tag(path=args.three) if args.three else page.add_script_tag(url=CDN)
        page.add_script_tag(content=SETUP)
        page.evaluate("([d, w, h, v]) => setupBody(d, w, h, v)", [data, width, height, list(VIEW)])
        for angle in ANGLES:
            url = page.evaluate("([a, o]) => renderAngle(String(a), String(o))", [angle, OTHER_ARM_DEG])
            image = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGBA")
            image.save(OUT / f"arm_{angle:03d}.png", optimize=True)
        browser.close()
    meta = {"size": [width, height], "angles": ANGLES,
            # Screen-left and screen-right shoulder joints (the body faces the viewer).
            "shoulders": [to_px(-JOINT[0], JOINT[1]), to_px(JOINT[0], JOINT[1])],
            "source": "body-1/Male-low.OBJ"}
    (OUT / "silhouette.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"{len(ANGLES)} frames, {width}x{height}, written to {OUT}")


if __name__ == "__main__":
    main()
