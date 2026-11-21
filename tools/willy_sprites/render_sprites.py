"""Regenerate Willy's sprite layers (assets/willy/) from willy_model.js.

The app never runs three.js: it composites these pre-rendered, transparent
layers with OpenCV, so Willy stays on screen even with --no-avatars.

    python -m pip install playwright && python -m playwright install chromium
    python tools/willy_sprites/render_sprites.py

Options: --three-dir DIR uses a local three@0.147.0 package instead of jsDelivr;
--browser PATH uses an installed Chrome.
"""
import argparse
import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "assets" / "willy"
CDN = "https://cdn.jsdelivr.net/npm/three@0.147.0/"
FILES = ("build/three.min.js", "examples/js/environments/RoomEnvironment.js")
WIDTH, HEIGHT = 560, 588          # Orthographic frame: x -1.95..1.95, y -0.07..4.03 scene units
ARM_ANGLES = list(range(0, 170, 10))
WAVE_ELBOWS = (-40, -20, 0, 20, 40)

SETUP = """
window.setupWilly = (W, H) => {
  THREE.ColorManagement.legacyMode = false;
  const canvas = document.createElement('canvas'); canvas.width = W; canvas.height = H; document.body.appendChild(canvas);
  const r = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true, preserveDrawingBuffer: true});
  r.setPixelRatio(1); r.setSize(W, H, false); r.setClearColor(0x000000, 0);
  r.outputEncoding = THREE.sRGBEncoding; r.toneMapping = THREE.ACESFilmicToneMapping; r.toneMappingExposure = 1.0;
  const scene = new THREE.Scene();
  scene.environment = new THREE.PMREMGenerator(r).fromScene(new THREE.RoomEnvironment(), 0.04).texture;
  const cam = new THREE.OrthographicCamera(-1.95, 1.95, 2.05, -2.05, 0.1, 50);
  cam.position.set(0, 1.98 + 0.9, 8); cam.lookAt(0, 1.98, 0);
  const key = new THREE.DirectionalLight(0xffffff, 1.25); key.position.set(3, 6, 4);
  const rim = new THREE.DirectionalLight(0x9fe8f0, 0.9); rim.position.set(-4, 3, -4);
  const hemi = new THREE.HemisphereLight(0xffffff, 0x9cc7c4, 0.35);
  [key, rim, hemi].forEach(l => { l.layers.enableAll(); scene.add(l); });
  const w = buildWilly(THREE); scene.add(w.willy);
  const ids = {body: 1, head: 2, armL: 3, armR: 4};
  w.willy.traverse(o => { if (o.isMesh) o.layers.set(ids[o.userData.layer]); });
  window.renderLayer = (cfg) => {
    w.setArm('L', cfg.armL ?? 0, cfg.elbowL ?? 0); w.setArm('R', cfg.armR ?? 0, cfg.elbowR ?? 0);
    w.setFace(cfg.eyes ?? 'open', cfg.mouth ?? 'smile');
    cam.layers.set(ids[cfg.layer]);
    r.render(scene, cam);
    return canvas.toDataURL('image/png');
  };
  window.projectPoint = (x, y, z) => {
    w.willy.updateMatrixWorld(true); cam.updateMatrixWorld(true);
    const v = new THREE.Vector3(x, y, z).project(cam);
    return [(v.x + 1) / 2 * W, (1 - v.y) / 2 * H];
  };
};
"""


def layers():
    for eyes in ("open", "blink", "happy"):
        for mouth in ("smile", "talk1", "talk2"):
            yield f"head_{eyes}_{mouth}", {"layer": "head", "eyes": eyes, "mouth": mouth}
    yield "body", {"layer": "body"}
    for side in ("L", "R"):
        for angle in ARM_ANGLES:
            yield f"arm{side}_{angle:03d}", {"layer": f"arm{side}", f"arm{side}": angle}
        for elbow in WAVE_ELBOWS:
            yield f"arm{side}_wave_{elbow:+03d}", {"layer": f"arm{side}", f"arm{side}": 150, f"elbow{side}": elbow}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--three-dir", type=Path, help="Local three@0.147.0 package directory")
    parser.add_argument("--browser", help="Chrome/Chromium executable")
    args = parser.parse_args()
    from PIL import Image
    import io
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"canvas": [WIDTH, HEIGHT], "layers": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.browser, args=["--use-gl=swiftshader", "--ignore-gpu-blocklist"])
        page = browser.new_page()
        page.goto((HERE / "render.html").as_uri())
        for name in FILES:
            if args.three_dir:
                page.add_script_tag(path=str(args.three_dir / name))
            else:
                page.add_script_tag(url=CDN + name)
        page.add_script_tag(path=str(HERE / "willy_model.js"))
        page.add_script_tag(content=SETUP)
        page.evaluate(f"setupWilly({WIDTH}, {HEIGHT})")
        meta["neck"] = page.evaluate("projectPoint(0, 1.9, 0)")
        meta["feet"] = page.evaluate("projectPoint(0, 0, 0)")
        for name, cfg in layers():
            url = page.evaluate("cfg => renderLayer(cfg)", cfg)
            image = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGBA")
            box = image.getchannel("A").getbbox()
            if box is None:
                raise RuntimeError(f"Empty layer: {name}")
            image.crop(box).save(OUT / f"{name}.png", optimize=True)
            meta["layers"][name] = list(box[:2])
        browser.close()
    (OUT / "willy.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(f"{len(meta['layers'])} layers written to {OUT}")


if __name__ == "__main__":
    main()
