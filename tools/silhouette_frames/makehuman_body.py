"""Build the CC0 MakeHuman bodies (adult male and female) for the silhouette frames.

MakeHuman's assets (base mesh, targets, skeleton and skin weights) have been CC0 since
September 2020 (LICENSE.ASSETS.md in its repository; each file says so in its header). This
script reads them from a checkout of https://github.com/makehumancommunity/makehuman and
writes, for each body, what tools/silhouette_frames/render_frames.py needs:

    <out>/makehuman-<gender>.obj          the body, centimetres, Y up, feet at 0, facing +Z
    <out>/makehuman-<gender>-weights.npz  per vertex: arm (moves with the humerus) and
                                          girdle (moves with the shoulder girdle)
    <out>/makehuman-<gender>.json         joints measured on the skeleton, for render_frames --body

Skin weights come from MakeHuman's rig, relaxed over the shoulder cap (see `relax`). No
MakeHuman code is used (it is AGPL): only its data files are read.

    git clone --depth 1 https://github.com/makehumancommunity/makehuman
    python tools/silhouette_frames/makehuman_body.py makehuman/makehuman/data --out build/bodies
    python tools/silhouette_frames/render_frames.py --body build/bodies/makehuman-male.json \\
        --out assets/silhouette/makehuman-male
"""
import argparse
import json
from pathlib import Path

import numpy as np

from render_frames import cotangent_laplacian, harmonic

RACES = ("african", "asian", "caucasian")   # MakeHuman's default mixes the three equally
# Nipples flattened: the body is a guide, not an anatomy plate.
SMOOTHING_TARGETS = (("breast/nipple-size-decr.target", 1.), ("breast/nipple-point-decr.target", 1.))
SOFT_ELBOW_DEG = 15.   # the rest pose bends the elbow ~47 deg, forearm forward: opened to a soft bend
# Bones by name prefix (each has a .L and a .R): upperarm01-02, lowerarm01-02, wrist,
# metacarpal1-4, finger1-1 to finger5-3; the girdle is the clavicle and shoulder01 (acromion
# to the humeral head).
ARM_BONES = ("upperarm", "lowerarm", "wrist", "metacarpal", "finger")
FOREARM_BONES = ARM_BONES[1:]
GIRDLE_BONES = ("clavicle", "shoulder")
BODY_VERTICES = 13380  # the "body" group: the first vertices of base.obj (the rest are helpers)
# Relaxed weights: free within these distances of the shoulder joint, in shoulder half-widths
# (the joint's distance from the midline). Elsewhere the rig's 0s and 1s are kept.
ARM_FREE, GIRDLE_FREE = .75, 1.2


def load_base(data):
    """Vertices (decimetres) and the faces of the body group."""
    vertices, faces, group = [], [], None
    for line in (data / "3dobjs" / "base.obj").read_text().splitlines():
        if line.startswith("v "):
            vertices.append([float(t) for t in line.split()[1:4]])
        elif line.startswith("g "):
            group = line.split(None, 1)[1].strip()
        elif line.startswith("f ") and group == "body":
            faces.append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])
    return np.asarray(vertices), faces


def load_target(path):
    """A MakeHuman target: sparse vertex offsets, one 'index dx dy dz' line each."""
    rows = [line.split() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    if not rows:
        return np.zeros(0, int), np.zeros((0, 3))
    return np.asarray([int(r[0]) for r in rows]), np.asarray([[float(t) for t in r[1:4]] for r in rows])


def target_weights(gender):
    """Targets of a 25-year-old adult of average muscle, weight, height and proportions.

    MakeHuman's macro sliders at their defaults (age 25, every other slider in the middle, the
    three ethnic mixes equal) select only the ethnic targets of the chosen gender: the
    'universal' young-average targets are empty, and height, proportions and cup size have
    no target in the middle of their range.
    """
    return [(f"macrodetails/{race}-{gender}-young.target", 1. / len(RACES)) for race in RACES] + list(SMOOTHING_TARGETS)


def build_shape(data, gender):
    vertices, faces = load_base(data)
    for name, weight in target_weights(gender):
        index, delta = load_target(data / "targets" / name)
        vertices[index] += weight * delta
    return vertices, faces


def joints(data, vertices):
    """Joint positions of the default skeleton: each is the centre of a set of helper vertices."""
    skeleton = json.loads((data / "rigs" / "default.mhskel").read_text())
    return {name: vertices[index].mean(axis=0) for name, index in skeleton["joints"].items()}


def bone_weights(data, n):
    """Per-bone skin weights of the default rig, as dense arrays over the first n vertices."""
    raw = json.loads((data / "rigs" / "default_weights.mhw").read_text())["weights"]
    out = {}
    for bone, pairs in raw.items():
        w = np.zeros(n)
        index = np.asarray([p[0] for p in pairs])
        keep = index < n
        w[index[keep]] = np.asarray([p[1] for p in pairs])[keep]
        out[bone] = w
    return out


def summed(weights, prefixes, side):
    return np.clip(sum(w for bone, w in weights.items()
                       if bone.endswith("." + side) and bone.split(".")[0].startswith(prefixes)), 0., 1.)


def rotate(points, axis, angle, centre):
    """Rotate each point about `axis` (unit) through `centre` by its own `angle` (radians)."""
    v = points - centre
    cos, sin = np.cos(angle)[:, None], np.sin(angle)[:, None]
    return centre + v * cos + np.cross(axis, v) * sin + axis * (v @ axis)[:, None] * (1 - cos)


def straighten_elbows(vertices, weights, joint, bend=SOFT_ELBOW_DEG):
    """Open both elbows to a soft bend, as a lateral raise wants (skinned with the rig's weights)."""
    out = vertices.copy()
    for side in "LR":
        shoulder, elbow, wrist = (joint[f"{b}.{side}____head"] for b in ("upperarm01", "lowerarm01", "wrist"))
        upper, fore = elbow - shoulder, wrist - elbow
        current = np.degrees(np.arccos(upper @ fore / np.linalg.norm(upper) / np.linalg.norm(fore)))
        axis = np.cross(upper, fore)
        axis /= np.linalg.norm(axis)
        out = rotate(out, axis, -np.radians(current - bend) * summed(weights, FOREARM_BONES, side), elbow)
    return out


def relax(vertices, triangles, joint, arm, girdle):
    """The rig's weights, relaxed over the shoulder cap by a harmonic solve.

    The rig turns the shoulder cap over a narrow band, which dents the top of the shoulder past
    120 deg. Near the joint the weights are solved again as the smoothest field over the surface
    (as render_frames does for its own body), held at 1 where the rig says arm and at 0 where it
    says trunk, further away. The deltoid then turns with the humerus and blends into the
    trapezius and the collarbone without a crease.
    """
    laplacian = cotangent_laplacian(vertices, triangles)
    half = joint[0]
    local = np.abs(vertices[:, :1]) * [1., 0., 0.] + vertices * [0., 1., 1.]
    dist = np.linalg.norm(local - joint, axis=1)
    arm = harmonic(laplacian, arm > .98, (arm < .02) & (dist > ARM_FREE * half))
    girdle = np.maximum(harmonic(laplacian, girdle > .98, (girdle < .02) & (dist > GIRDLE_FREE * half)), arm)
    return arm, girdle


def build(data, gender, out):
    vertices, faces = build_shape(data, gender)
    joint = joints(data, vertices)
    weights = bone_weights(data, BODY_VERTICES)
    vertices = straighten_elbows(vertices[:BODY_VERTICES], weights, joint)  # the joints used below do not move
    floor = vertices[:, 1].min()
    to_cm = lambda p: (np.asarray(p) - [0., floor, 0.]) * 10.   # decimetres to centimetres, feet at 0
    cm = to_cm(vertices)
    gh, elbow = to_cm(joint["upperarm01.L____head"]), to_cm(joint["lowerarm01.L____head"])
    upper = (elbow - gh) / np.linalg.norm(elbow - gh)
    triangles = np.asarray([[f[0], f[k], f[k + 1]] for f in faces for k in range(1, len(f) - 1)], np.int32)
    arm = np.maximum(summed(weights, ARM_BONES, "L"), summed(weights, ARM_BONES, "R"))
    girdle = np.clip(arm + np.maximum(summed(weights, GIRDLE_BONES, "L"), summed(weights, GIRDLE_BONES, "R")), 0., 1.)
    arm, girdle = relax(cm, triangles, gh, arm, girdle)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"makehuman-{gender}"
    with open(out / f"{stem}.obj", "w", encoding="utf-8") as f:
        f.write(f"# MakeHuman base mesh (CC0 1.0), adult {gender}, built by makehuman_body.py\n")
        f.writelines(f"v {x:.3f} {y:.3f} {z:.3f}\n" for x, y, z in cm)
        f.writelines("f " + " ".join(str(i + 1) for i in face) + "\n" for face in faces)
    np.savez_compressed(out / f"{stem}-weights.npz", arm=arm.astype(np.float32), girdle=girdle.astype(np.float32))
    meta = {
        "obj": f"{stem}.obj", "weights": f"{stem}-weights.npz",
        "source": f"MakeHuman base mesh, adult {gender} (CC0 1.0)",
        "height_cm": round(float(cm[:, 1].max()), 1),
        "joint": gh.round(2).tolist(),                                       # glenohumeral joint (+x side)
        "sterno": to_cm(joint["clavicle.L____head"]).round(2).tolist(),     # sternoclavicular joint
        "hips_y": round(float(to_cm(joint["upperleg01.L____head"])[1]), 2),  # height of the hip joints
        "upper_arm": upper.round(4).tolist(),
        "rest_deg": round(float(np.degrees(np.arccos(-upper[1]))), 1),
        "elbow_deg": SOFT_ELBOW_DEG,
    }
    (out / f"{stem}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data", type=Path, help="makehuman/data folder of a MakeHuman checkout")
    parser.add_argument("--out", type=Path, default=Path("build/bodies"))
    parser.add_argument("--gender", choices=("male", "female"), action="append")
    args = parser.parse_args()
    for gender in args.gender or ("male", "female"):
        print(gender, build(args.data, gender, args.out))


if __name__ == "__main__":
    main()
