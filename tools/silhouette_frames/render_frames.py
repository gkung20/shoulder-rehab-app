"""Render the 3D guide silhouette frames (assets/silhouette/) from a full-body OBJ.

The OBJ (body-1/Male-low.OBJ, A-pose, Y up, centimetres, facing +Z) is not
stored in the repository: only the rendered frames are. Each frame shows the
body facing the patient with the screen-right arm raised to one angle
(0-160 deg, every 5 deg) like a well-performed lateral raise: in the scapular
plane, elbow soft (as in the A-pose), shoulder blade rotating with a 2:1 scapulohumeral rhythm
after 30 deg and no shrug. Skinning uses harmonic weights (the deltoid moves with the humerus)
followed by delta mush around the shoulders, which removes creases at the top of the shoulder. The app flips the frames for the left side. Pixels hold
channels the app recolours at runtime:
    R = diffuse shading, G = fresnel rim, B = unused, A = coverage.

    python -m pip install playwright && python -m playwright install chromium
    python tools/silhouette_frames/render_frames.py C:/Users/you/Desktop/body-1/Male-low.OBJ

Phase 11: the CC0 MakeHuman bodies (male and female) go through the same posing and shading.
tools/silhouette_frames/makehuman_body.py builds each body with its joints measured on
MakeHuman's skeleton and its skin weights taken from MakeHuman's rig (both CC0); --body uses
them instead of the harmonic weights and frames the view around the body:

    python tools/silhouette_frames/render_frames.py --body build/bodies/makehuman-female.json \
        --out assets/silhouette/makehuman-female
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
SOURCE = "body-1/Male-low.OBJ"
# Delta mush works within this distance of the shoulder joint (cm, for 22 cm from the midline;
# scaled with the shoulders of another body).
MUSH_RADII = (24., 34.)


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
    y = local[:, 1]
    on_arm = (along > 13.) & (radial < np.where(beyond_elbow, 17., 8.))
    # The deltoid wraps the humeral head and moves with it; the trapezius and upper chest stay put.
    # This puts the skin transition where it belongs (acromion line on top, axillary folds below)
    # instead of half-rotating the shoulder cap, which made it bunch up like a pad.
    on_arm |= (x > 23.5) & (y > 124.) & (dist < 14.)
    trunk = ((dist > 17.) & ((radial > np.where(beyond_elbow, 21., 12.)) | (along < 0.))) | (x < 8.)
    trunk |= (x < 16.5) & (y > 132.) & ~on_arm
    arm = harmonic(laplacian, on_arm, trunk & ~on_arm)
    shoulder = on_arm | (dist < 7.)
    still = (x < 7.) | (y > 160.) | ((dist > 24.) & ~on_arm)
    girdle = np.maximum(harmonic(laplacian, shoulder, still & ~shoulder), arm)
    return arm.astype(np.float32), girdle.astype(np.float32)


def shoulder_angles(elevation, rest=None):
    """Split a humerothoracic elevation into girdle lift and glenohumeral rotation (degrees)."""
    rest = REST_DEG if rest is None else rest
    scapular = max(0., elevation - 30.) / 3.          # 2:1 after the 30 deg setting phase
    girdle = GIRDLE_LIFT_PER_SCAPULAR_DEG * scapular
    return girdle, elevation - girdle - rest


def rodrigues(points, axis, angle, centre):
    """Rotate each point about `axis` (unit, per point) through `centre` by its own `angle` (radians)."""
    v = points - centre
    cos, sin = np.cos(angle)[:, None], np.sin(angle)[:, None]
    return centre + v * cos + np.cross(axis, v) * sin + axis * np.einsum("ij,ij->i", axis, v)[:, None] * (1 - cos)


def pose_vertices(vertices, arm, girdle, active_deg, other_deg=OTHER_ARM_DEG):
    """Skin the body: humerus in the scapular plane, then the shoulder girdle (both blended per vertex)."""
    out = vertices.astype(np.float64).copy()
    side = np.where(vertices[:, 0] >= 0, 1., -1.)
    phi = np.radians(SCAPULAR_PLANE_DEG)
    for s, deg in ((1., active_deg), (-1., other_deg)):
        m = side == s
        lift, gh = shoulder_angles(deg)
        axis = np.tile([-np.sin(phi), 0., s * np.cos(phi)], (m.sum(), 1))
        out[m] = rodrigues(out[m], axis, np.radians(gh) * arm[m], np.array([s * JOINT[0], JOINT[1], JOINT[2]]))
        axis = np.tile([0., 0., s], (m.sum(), 1))
        out[m] = rodrigues(out[m], axis, np.radians(lift) * girdle[m], np.array([s * STERNO[0], STERNO[1], STERNO[2]]))
    return out


class DeltaMush:
    """Delta mush (Mancewicz et al., 2014), the production fix for skinning creases.

    The posed mesh is smoothed, then each vertex's rest-pose detail (its offset from the smoothed
    rest mesh, stored in a local tangent frame) is added back in the posed frame. Pinches and kinks
    vanish while muscles and surface detail are kept. Applied around the shoulders only.
    """

    def __init__(self, vertices, faces, iterations=35, strength=.5):
        from scipy import sparse
        n = len(vertices)
        edges = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
        adjacency = sparse.csr_matrix((np.ones(2 * len(edges)), (np.r_[edges[:, 0], edges[:, 1]],
                                                                 np.r_[edges[:, 1], edges[:, 0]])), shape=(n, n))
        adjacency.data[:] = 1.
        self.average = sparse.diags(1. / np.asarray(adjacency.sum(axis=1)).ravel()) @ adjacency
        self.neighbour = np.array([row[0] for row in adjacency.tolil().rows])
        self.faces, self.iterations, self.strength = faces, iterations, strength
        rest = vertices.astype(np.float64)
        smooth = self._smooth(rest)
        t, b, n_ = self._frames(smooth)
        offset = rest - smooth
        self.delta = np.stack([np.einsum("ij,ij->i", offset, f) for f in (t, b, n_)], axis=1)
        local = np.abs(rest[:, 0:1]) * [1, 0, 0] + rest * [0, 1, 1]
        near, far = (r * JOINT[0] / 22. for r in MUSH_RADII)
        self.mask = (1 - smoothstep(near, far, np.linalg.norm(local - np.array(JOINT), axis=1)))[:, None]

    def _smooth(self, points):
        for _ in range(self.iterations):
            points = (1 - self.strength) * points + self.strength * (self.average @ points)
        return points

    def _frames(self, points):
        f = self.faces
        face_normal = np.cross(points[f[:, 1]] - points[f[:, 0]], points[f[:, 2]] - points[f[:, 0]])
        normal = np.zeros_like(points)
        for k in range(3):
            np.add.at(normal, f[:, k], face_normal)
        normal /= np.linalg.norm(normal, axis=1, keepdims=True) + 1e-12
        tangent = points[self.neighbour] - points
        tangent -= normal * np.einsum("ij,ij->i", tangent, normal)[:, None]
        tangent /= np.linalg.norm(tangent, axis=1, keepdims=True) + 1e-12
        return tangent, np.cross(normal, tangent), normal

    def __call__(self, posed):
        smooth = self._smooth(posed)
        t, b, n_ = self._frames(smooth)
        rebuilt = smooth + self.delta[:, :1] * t + self.delta[:, 1:2] * b + self.delta[:, 2:] * n_
        return posed + self.mask * (rebuilt - posed)


SETUP = """
window.setupBody = (data, W, H, view) => {
  const canvas = document.createElement('canvas'); canvas.width = W; canvas.height = H; document.body.appendChild(canvas);
  const r = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true, preserveDrawingBuffer: true});
  r.setPixelRatio(1); r.setSize(W, H, false); r.setClearColor(0x000000, 0);
  const cam = new THREE.OrthographicCamera(view[0], view[1], view[3], view[2], -500, 500);
  cam.position.set(0, 0, 200); cam.lookAt(0, 0, 0);
  const geo = new THREE.BufferGeometry();
  const pos = new THREE.BufferAttribute(new Float32Array(data.positions), 3);
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
  // Vertices are posed in Python (skinning + delta mush); the page only shades and renders them.
  window.renderPositions = (p) => {
    pos.array.set(p); pos.needsUpdate = true; geo.computeVertexNormals();
    r.render(scene, cam);
    return canvas.toDataURL('image/png');
  };
};
"""


def load_body(path):
    """A body from makehuman_body.py: its mesh, rig weights and joints (sets the skeleton globals)."""
    global JOINT, STERNO, UPPER_ARM, REST_DEG, SOURCE
    body = json.loads(Path(path).read_text(encoding="utf-8"))
    JOINT, STERNO, UPPER_ARM = (tuple(body[k]) for k in ("joint", "sterno", "upper_arm"))
    REST_DEG, SOURCE = float(body["rest_deg"]), body["source"]
    vertices, faces = load_obj(Path(path).parent / body["obj"])
    weights = np.load(Path(path).parent / body["weights"])
    return vertices, faces, weights["arm"], weights["girdle"]


def proportions(vertices, arm, posed_frames, hips_y=None):
    """Body proportions in shoulder widths, as src/silhouette.py frames the half body.

    head: top of the head above the shoulder joints; reach: fingertips of the hanging arm below
    them; arm_side: hand of the arm raised to 90-100 deg, from the middle of the body;
    other_side: the hanging arm on the other side; hips: the hip joints below the shoulders.
    """
    width = 2 * JOINT[0]
    pose = dict(zip(ANGLES, posed_frames))
    rest = pose[0]
    hand_side = (arm > .98) & (vertices[:, 0] > 0)
    out = {"head": (rest[:, 1].max() - JOINT[1]) / width,
           "reach": (JOINT[1] - rest[hand_side, 1].min()) / width,
           "arm_side": max(p[:, 0].max() for a, p in pose.items() if 90 <= a <= 100) / width,
           "other_side": max(-p[:, 0].min() for p in posed_frames) / width}
    if hips_y is not None:
        out["hips"] = (JOINT[1] - hips_y) / width
    return {k: round(float(v), 3) for k, v in out.items()}


def framed_view(posed_frames, margin=4.):
    """The smallest view (whole cm) holding the body in every pose, with a margin."""
    points = np.concatenate([p[:, :2] for p in posed_frames])
    (x0, y0), (x1, y1) = points.min(axis=0) - margin, points.max(axis=0) + margin
    return tuple(float(v) for v in (np.floor(x0), np.ceil(x1), np.floor(y0), np.ceil(y1)))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("obj", type=Path, nargs="?", help="Body OBJ (A-pose, cm, Y up, facing +Z)")
    parser.add_argument("--body", type=Path, help="Body .json from makehuman_body.py (joints and rig weights)")
    parser.add_argument("--three", help="Local three.min.js (r147) instead of jsDelivr")
    parser.add_argument("--browser", help="Chrome/Chromium executable")
    parser.add_argument("--joint", help="Override the shoulder joint, x,y,z in cm (for tuning)")
    parser.add_argument("--angles", help="Render only these angles, comma separated (for tuning)")
    parser.add_argument("--out", type=Path, help="Output folder (default: assets/silhouette)")
    args = parser.parse_args()
    global JOINT, ANGLES, OUT, VIEW
    if not args.obj and not args.body:
        parser.error("give a body OBJ or --body")
    if args.body:
        vertices, faces, arm, girdle = load_body(args.body)
    if args.joint:
        JOINT = tuple(float(t) for t in args.joint.split(","))
    if args.angles:
        ANGLES = [int(t) for t in args.angles.split(",")]
    if args.out:
        OUT = args.out
    from PIL import Image
    from playwright.sync_api import sync_playwright
    if not args.body:
        vertices, faces = load_obj(args.obj)
        arm, girdle = skin_weights(vertices, faces)
    mush = DeltaMush(vertices, faces)
    posed_frames = [mush(pose_vertices(vertices, arm, girdle, angle)).astype(np.float32) for angle in ANGLES]
    if args.body:
        VIEW = framed_view(posed_frames)
        hips_y = json.loads(args.body.read_text(encoding="utf-8")).get("hips_y")
    data = {"positions": vertices.ravel().tolist(), "indices": faces.ravel().tolist()}
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
        for angle, posed in zip(ANGLES, posed_frames):
            url = page.evaluate("p => renderPositions(p)", posed.ravel().tolist())
            image = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGBA")
            image.save(OUT / f"arm_{angle:03d}.png", optimize=True)
        browser.close()
    meta = {"size": [width, height], "angles": ANGLES,
            # Screen-left and screen-right shoulder joints (the body faces the viewer).
            "shoulders": [to_px(-JOINT[0], JOINT[1]), to_px(JOINT[0], JOINT[1])],
            "source": SOURCE}
    if args.body and 0 in ANGLES and any(90 <= a <= 100 for a in ANGLES):
        meta["proportions"] = proportions(vertices, arm, posed_frames, hips_y)
    (OUT / "silhouette.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"{len(ANGLES)} frames, {width}x{height}, written to {OUT}")


if __name__ == "__main__":
    main()
