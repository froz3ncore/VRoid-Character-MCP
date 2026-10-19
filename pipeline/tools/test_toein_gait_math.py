"""Numerical checks run with the NumPy-enabled Blender Python runtime."""
import numpy as np
from toein_gait_math import solve_leg,between,yaw

def main():
    rng=np.random.default_rng(4217)
    for _ in range(300):
        hip=np.array([0.,.9,0.]);knee=np.array([0.,.5,.08]);ankle=np.array([0.,.1,.01]);target=ankle+rng.uniform(-.025,.025,3)
        k,f,ok=solve_leg(hip,knee,ankle,target,2)
        if ok:assert np.linalg.norm(f-target)<1e-10
        assert abs(np.linalg.norm(k-hip)-np.linalg.norm(knee-hip))<1e-10
        assert abs(np.linalg.norm(f-k)-np.linalg.norm(ankle-knee))<1e-10
        rotation=between(knee-hip,k-hip)
        assert np.linalg.norm(rotation@(knee-hip)-(k-hip))<1e-10
        assert np.linalg.norm(rotation.T@rotation-np.eye(3))<1e-10
    _,_,ok=solve_leg(np.array([0.,1,0]),np.array([0.,.5,.05]),np.array([0.,0,0]),np.array([2.,0,0]),2);assert not ok
    for axis in np.eye(3):assert np.linalg.norm(between(axis,-axis)@axis+axis)<1e-10
    assert np.linalg.norm(yaw(6)@yaw(-6)-np.eye(3))<1e-10
    print('300 independent reachable/length/rotation checks, unreachable and opposite-axis cases passed')
if __name__=='__main__':main()
