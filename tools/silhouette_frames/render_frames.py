"""Render the 3D guide silhouette frames (assets/silhouette/) from a full-body OBJ.

The OBJ (body-1/Male-low.OBJ, A-pose, Y up, centimetres, facing +Z) is not
stored in the repository: only the rendered frames are. Each frame shows the
body facing the patient with the screen-right arm abducted to one angle
(0-160 deg, every 5 deg); the app flips them for the left side. Pixels hold
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
JOINT = (21.5, 141.0, -7.0)     # left shoulder joint (+x side), cm
REST_DEG = 22.0                 # arm abduction of the A-pose
OTHER_ARM_DEG = 8.0             # the arm that is not exercising hangs relaxed
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


def arm_weights(v):
    """How much each vertex follows its arm: 1 on the arms, 0 on the torso, smooth across the shoulders."""
    x, y = np.abs(v[:, 0]), v[:, 1]
    # Under the armpit the arm is apart from the torso; lower down, keep clear of the thighs.
    low = smoothstep(103., 112., y)
    below = smoothstep(18., 22., x) * low + smoothstep(25., 31., x) * (1 - low)
    above = smoothstep(14., 24., x)          # shoulder: blend over the deltoid
    t = smoothstep(117., 129., y)
    w = below * (1 - t) + above * t
    w *= 1 - smoothstep(158., 166., y)       # never the head or neck
    w *= smoothstep(66., 72., y)             # never the legs or feet (fingertips end near 78 cm)
    return w.astype(np.float32)


SETUP = """
window.setupBody = (data, W, H, view) => {
  const canvas = document.createElement('canvas'); canvas.width = W; canvas.height = H; document.body.appendChild(canvas);
  const r = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true, preserveDrawingBuffer: true});
  r.setPixelRatio(1); r.setSize(W, H, false); r.setClearColor(0x000000, 0);
  const cam = new THREE.OrthographicCamera(view[0], view[1], view[3], view[2], -500, 500);
  cam.position.set(0, 0, 200); cam.lookAt(0, 0, 0);
  const base = new Float32Array(data.positions), w = new Float32Array(data.weights);
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
  const J = data.joint;
  window.renderAngle = (deg) => {
    const dR = (deg - data.rest) * Math.PI / 180, dL = (data.other - data.rest) * Math.PI / 180;
    for (let i = 0; i < w.length; i++) {
      const side = base[3*i] >= 0 ? 1 : -1, jx = side * J[0];
      const a = side * (side > 0 ? dR : dL) * w[i], c = Math.cos(a), s = Math.sin(a);
      const x = base[3*i] - jx, y = base[3*i+1] - J[1];
      pos.array[3*i] = jx + c*x - s*y; pos.array[3*i+1] = J[1] + s*x + c*y; pos.array[3*i+2] = base[3*i+2];
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
    data = {"positions": vertices.ravel().tolist(), "indices": faces.ravel().tolist(),
            "weights": arm_weights(vertices).tolist(), "joint": JOINT, "rest": REST_DEG, "other": OTHER_ARM_DEG}
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
            url = page.evaluate("a => renderAngle(a)", angle)
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
