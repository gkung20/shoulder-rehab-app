"""Render the 3D guide silhouette frames (assets/silhouette/) from a full-body OBJ.

The OBJ (body-1/Male-low.OBJ, A-pose, Y up, centimetres, facing +Z) is not
stored in the repository: only the rendered frames are. Each frame shows the
body facing the patient with the screen-right arm raised to one angle
(0-160 deg, every 5 deg) like a well-performed lateral raise: in the scapular
plane, elbow soft (as in the A-pose), shoulder blade rotating with a 2:1 scapulohumeral rhythm
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
# Skeleton of the +x side, measured on the mesh (slice centroids of the upper arm and forearm).
JOINT = (22.0, 145.0, -10.0)    # glenohumeral joint: centre of the humeral head, under the acromion
UPPER_ARM = (0.435, -0.894, 0.108)  # humerus direction in the A-pose (26 deg abduction)
STERNO = (3.0, 150.0, 2.0)      # sternoclavicular pivot of the shoulder girdle
REST_DEG = 26.0                 # humerus abduction of the A-pose
OTHER_ARM_DEG = 8               # the arm that is not exercising hangs relaxed
SCAPULAR_PLANE_DEG = 25.0       # lateral raise in the scapular plane, 20-30 deg in front of the body
# The A-pose elbow is already soft (~22 deg), as a lateral raise wants: it is kept, not re-bent.
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


def cotangent_laplacian(vertices, faces):
    """Symmetric cotangent Laplacian (negative cotangents clamped, so harmonic weights stay in [0, 1])."""
    from scipy import sparse
    rows, cols, vals = [], [], []
    for a, b, c in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
        i, j, k = faces[:, a], faces[:, b], faces[:, c]
        u, w = vertices[i] - vertices[k], vertices[j] - vertices[k]
        cot = np.einsum("ij,ij->i", u, w) / np.maximum(np.linalg.norm(np.cross(u, w), axis=1), 1e-12)
        cot = np.maximum(cot, 0.) * .5
        rows += [i, j]; cols += [j, i]; vals += [cot, cot]
    n = len(vertices)
    weights = sparse.csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    return sparse.diags(np.asarray(weights.sum(axis=1)).ravel()) - weights


def harmonic(laplacian, ones, zeros):
    """Smoothest field over the surface that is 1 on `ones` and 0 on `zeros` (Laplace equation)."""
    from scipy.sparse.linalg import spsolve
    n = laplacian.shape[0]
    fixed = ones | zeros
    free = ~fixed
    values = np.zeros(n)
    values[ones] = 1.
    rhs = -laplacian[free][:, fixed] @ values[fixed]
    values[free] = spsolve(laplacian[free][:, free].tocsc(), rhs)
    return np.clip(values, 0., 1.)


def skin_weights(vertices, faces):
    """Harmonic skin weights for the humerus and the shoulder girdle, both sides.

    Weights are fixed only where the answer is obvious (the arm beyond mid-humerus = 1; the trunk,
    neck, head and legs = 0) and solved everywhere else on the surface. Because the solution follows
    the surface, the armpit separates cleanly and the deltoid blends smoothly into the trapezius,
    which is what a hand-tuned falloff could not do.
    """
    laplacian = cotangent_laplacian(vertices, faces)
    side = np.where(vertices[:, 0] >= 0, 1., -1.)
    local = vertices * np.stack([side, np.ones_like(side), np.ones_like(side)], axis=1)  # mirror to +x
    rel = local - np.array(JOINT)
    along = rel @ np.array(UPPER_ARM)
    radial = np.linalg.norm(rel - along[:, None] * np.array(UPPER_ARM), axis=1)
    dist = np.linalg.norm(rel, axis=1)
    x = local[:, 0]
    beyond_elbow = along > 30.          # forearm and hand: up to 14 cm off the humerus axis; thighs >= 25 cm
    on_arm = (along > 13.) & (radial < np.where(beyond_elbow, 17., 8.))
    trunk = ((dist > 17.) & ((radial > np.where(beyond_elbow, 21., 12.)) | (along < 0.))) | (x < 8.)
    arm = harmonic(laplacian, on_arm, trunk & ~on_arm)
    shoulder = on_arm | (dist < 7.)
    still = (x < 7.) | (local[:, 1] > 160.) | ((dist > 24.) & ~on_arm)
    girdle = np.maximum(harmonic(laplacian, shoulder, still & ~shoulder), arm)
    return arm.astype(np.float32), girdle.astype(np.float32)


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
  const wArm = new Float32Array(data.arm), wGirdle = new Float32Array(data.girdle);
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
      const S = [side*data.sterno[0], data.sterno[1], data.sterno[2]];
      // 1. glenohumeral elevation in the scapular plane (axis tilted so the arm travels forward of the body)
      if (wArm[i] > 0) v = rot(v, [-Math.sin(phi), 0, side*Math.cos(phi)], gh * D * wArm[i], J);
      // 2. shoulder girdle: small upward rotation about the sternoclavicular joint
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
    parser.add_argument("--joint", help="Override the shoulder joint, x,y,z in cm (for tuning)")
    parser.add_argument("--angles", help="Render only these angles, comma separated (for tuning)")
    parser.add_argument("--out", type=Path, help="Output folder (default: assets/silhouette)")
    args = parser.parse_args()
    global JOINT, ANGLES, OUT
    if args.joint:
        JOINT = tuple(float(t) for t in args.joint.split(","))
    if args.angles:
        ANGLES = [int(t) for t in args.angles.split(",")]
    if args.out:
        OUT = args.out
    from PIL import Image
    from playwright.sync_api import sync_playwright
    vertices, faces = load_obj(args.obj)
    arm, girdle = skin_weights(vertices, faces)
    poses = sorted(set(ANGLES) | {OTHER_ARM_DEG})
    data = {"positions": vertices.ravel().tolist(), "indices": faces.ravel().tolist(),
            "arm": arm.tolist(), "girdle": girdle.tolist(),
            "joint": JOINT, "sterno": STERNO, "rest": REST_DEG, "plane": SCAPULAR_PLANE_DEG,
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
