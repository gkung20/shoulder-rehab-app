"""Small cosmetic idle motion; never interpreted as observed body movement."""
import math


def natural_motion(seconds,phase=0.):
    """Degrees for head/chest and metres for breathing; feet stay planted."""
    t=max(0.,seconds) if math.isfinite(seconds) else 0.
    return {
        'head_yaw':3.0*math.sin(.47*t+phase),
        'head_pitch':.6*math.sin(.63*t+phase),
        'head_roll':.7*math.sin(.31*t+phase),
        'body_roll':.35*math.sin(.41*t+phase),
        'breathing':.0015*math.sin(2*math.pi*t/5.+phase),
    }


def rotation_xyz(x=0.,y=0.,z=0.):
    """Right-handed rotation matrix; arguments are degrees."""
    import numpy as np
    a,b,c=map(math.radians,(x,y,z))
    rx=np.array([[1,0,0],[0,math.cos(a),-math.sin(a)],[0,math.sin(a),math.cos(a)]])
    ry=np.array([[math.cos(b),0,math.sin(b)],[0,1,0],[-math.sin(b),0,math.cos(b)]])
    rz=np.array([[math.cos(c),-math.sin(c),0],[math.sin(c),math.cos(c),0],[0,0,1]])
    return rz@ry@rx
