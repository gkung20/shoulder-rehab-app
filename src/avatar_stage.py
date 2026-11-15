"""Offscreen doctor and user characters in the native patient window.

Local GLB skins use bind-space retargeting; procedural figures remain a fallback
when downloads are absent. Neither representation supplies assessment data.
"""
import numpy as np
import sys
from pathlib import Path
from src.avatar_motion import AvatarMotion
from src.avatar_life import natural_motion


def prepare_native_runtime():
    """Load the optional voice runtime before Panda's Windows native libraries.

    Importing ONNX Runtime after Panda3D can cause an access violation in its
    extension loader on Windows. Audio normally loads it lazily in a worker;
    preloading here also prevents that import racing with renderer startup.
    """
    if sys.platform == "win32":
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            pass  # Speech retains its existing unavailable/system fallback.


class AvatarStage:
    def __init__(self):
        prepare_native_runtime()
        from panda3d.core import loadPrcFileData, AmbientLight, DirectionalLight, OrthographicLens
        loadPrcFileData("rehab-avatar", "window-type offscreen\naudio-library-name null\nwin-size 1000 560\nframebuffer-multisample 1\nmultisamples 4\nsync-video false\nnotify-level warning")
        from direct.showbase.ShowBase import ShowBase
        self.base=ShowBase(windowType="offscreen")
        if self.base.win is None:
            self.base.destroy()
            raise RuntimeError("Le rendu 3D n’est pas disponible sur cet ordinateur.")
        self.buffer=self.base.win
        self.base.disableMouse()
        self.base.setBackgroundColor(.955,.958,.96,1)
        self.buffer.setClearColor((.955,.958,.96,1))
        lens=OrthographicLens()
        lens.setFilmSize(4.9,2.78)
        self.base.cam.node().setLens(lens)
        self.base.camLens=lens
        self.base.camera.setPos(0,-8,2.7)
        self.base.camera.lookAt(0,0,1.12)
        ambient=AmbientLight("soft-light")
        ambient.setColor((.55,.55,.55,1))
        self.base.render.setLight(self.base.render.attachNewNode(ambient))
        sun=DirectionalLight("key-light")
        sun.setColor((.45,.45,.45,1))
        light=self.base.render.attachNewNode(sun)
        light.setHpr(-25,-35,0)
        self.base.render.setLight(light)
        self.mesh=self._sphere()
        self.figures=[self._figure(-1.12,(.24,.38,.39,1)),self._figure(1.12,(.32,.39,.52,1))]
        self.characters={}
        self.user_gender="male"
        asset_dir=Path(__file__).resolve().parent.parent/'alo'
        patterns={'doctor':'*Doctor*.glb','male':'Stylized_Male_Character*.glb','female':'Stylized_Female_Character*.glb'}
        paths={key:next(asset_dir.glob(pattern),None) for key,pattern in patterns.items()}
        if all(paths.values()):
            from src.rigged_avatar import RiggedAvatar
            try:
                for key,path in paths.items():
                    self.characters[key]=RiggedAvatar(self.base.render,path,-1.12 if key=='doctor' else 1.12)
                for figure in self.figures:
                    next(iter(figure.values()))[0].getParent().removeNode()
                self.characters['female'].show(False)
                for x in (-1.12,1.12):
                    contact=self._part(self.base.render,(x,0,-.012),(.26,.17,.006),(.86,.87,.88,1))
                    contact.setLightOff()
            except Exception:
                self.base.destroy()
                raise
        self.motion=AvatarMotion()
        self.natural_time=0.
        self._natural_timestamp=None
        self.closed=False

    def set_user_gender(self,gender):
        if gender not in ('male','female'):
            raise ValueError("Avatar inconnu")
        self.user_gender=gender
        for key in ('male','female'):
            if key in self.characters:
                self.characters[key].show(key==gender)

    def _sphere(self):
        from panda3d.core import GeomVertexData, GeomVertexFormat, GeomVertexWriter, GeomTriangles, Geom, GeomNode
        import math
        data=GeomVertexData("mannequin",GeomVertexFormat.getV3n3(),Geom.UHStatic)
        vertex,normal=GeomVertexWriter(data,"vertex"),GeomVertexWriter(data,"normal")
        rows,cols=12,20
        for j in range(rows+1):
            phi=math.pi*j/rows
            for i in range(cols+1):
                theta=2*math.pi*i/cols
                xyz=(math.sin(phi)*math.cos(theta),math.sin(phi)*math.sin(theta),math.cos(phi))
                vertex.addData3(*xyz)
                normal.addData3(*xyz)
        triangles=GeomTriangles(Geom.UHStatic)
        for j in range(rows):
            for i in range(cols):
                a=j*(cols+1)+i
                b=a+cols+1
                triangles.addVertices(a,b,a+1)
                triangles.addVertices(a+1,b,b+1)
        geom=Geom(data)
        geom.addPrimitive(triangles)
        node=GeomNode("rounded-body")
        node.addGeom(geom)
        return node

    def _part(self,root,position,scale,color):
        part=root.attachNewNode(self.mesh.copySubgraph())
        part.setPos(*map(float,position))
        part.setScale(*map(float,scale))
        part.setColor(*color)
        return part

    def _figure(self,x,color):
        root=self.base.render.attachNewNode("figure")
        root.setX(x)
        self._part(root,(0,0,1.20),(.30,.16,.40),color)
        self._part(root,(0,0,.79),(.25,.15,.18),color)
        self._part(root,(0,0,1.68),(.085,.085,.12),color)
        self._part(root,(0,0,1.88),(.16,.14,.20),(.76,.77,.77,1))
        for sign in (-1,1):
            self._part(root,(sign*.14,0,.43),(.10,.11,.37),color)
            self._part(root,(sign*.14,-.045,.065),(.105,.19,.065),color)
        self._part(root,(0,0,-.025),(.51,.32,.025),(.85,.87,.88,1))
        arms={}
        for side in ("left","right"):
            arms[side]=[self._part(root,(0,0,0),(1,1,1),color) for _ in range(5)]
        return arms

    def _pose(self,figure,joints):
        for side,parts in figure.items():
            points=joints.get(side,(None,None,None))
            for node in parts:
                node.hide()
            for i,p in enumerate(points):
                if p is not None:
                    parts[i].show()
                    parts[i].setPos(*map(float,p))
                    parts[i].setScale(.085 if i < 2 else .07)
            for node,a,b in ((parts[3],points[0],points[1]),(parts[4],points[1],points[2])):
                if a is None or b is None:
                    continue
                length=float(np.linalg.norm(b-a))
                if length < .001:
                    continue
                node.show()
                node.setPos(*map(float,(a+b)/2))
                node.lookAt(*map(float,b))  # Panda's local Y axis points along the limb.
                node.setScale(.075,length/2,.075)

    def render(self,analysis,processor,mode,source_size,output_size):
        if self._natural_timestamp is not None and mode in ('ready','running'):
            self.natural_time+=max(0.,min(.1,analysis.timestamp_sec-self._natural_timestamp))
        self._natural_timestamp=analysis.timestamp_sec
        coach,user=self.motion.update(analysis,mode,*source_size,processor.arm,
            processor.config.abduction.target_min_deg,processor.config.timing.min_hold_time_sec,
            processor.config.filtering.min_landmark_visibility)
        tracked=any(all(p is not None for p in points) for points in user.values())
        display_pose=self.motion.display_pose
        self.resting_sides=self.motion.resting_sides
        self.detailed_hands=len(self.motion.hand_observations)
        if self.characters:
            self.characters['doctor'].pose(coach,observed=False,secondary=natural_motion(self.natural_time))
            character=self.characters[self.user_gender]
            character.root.clearColorScale()
            character.root.clearTransparency()
            character.pose(display_pose,observed=False,secondary=natural_motion(self.natural_time,phase=1.1),
                hands=self.motion.hand_observations,dt=self.motion.frame_dt)
        else:
            self._pose(self.figures[0],coach)
            self._pose(self.figures[1],display_pose)
        width,height=output_size
        # Buffer dimensions follow the display, keeping geometry sharp in full screen.
        if self.buffer.getXSize() != width or self.buffer.getYSize() != height:
            if not self.base.openMainWindow(type="offscreen",size=(width,height),keepCamera=True):
                raise RuntimeError("Impossible de redimensionner la scène 3D.")
            self.buffer=self.base.win
        self.base.cam.node().getLens().setFilmSize(4.9,4.9*height/width)
        self.base.graphicsEngine.renderFrame()
        self.base.graphicsEngine.renderFrame()
        texture=self.buffer.getScreenshot()
        if texture is None:
            raise RuntimeError("Impossible de lire le rendu 3D.")
        # Packed RGB bytes avoid per-pixel Python loops and an intermediate image.
        rgb=np.frombuffer(texture.getRamImageAs("RGB"),dtype=np.uint8).reshape(height,width,3)
        rgb=np.flipud(rgb).copy()
        return rgb,tracked

    def close(self):
        if not self.closed:
            self.base.destroy()
            self.closed=True
