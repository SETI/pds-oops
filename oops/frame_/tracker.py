################################################################################
# oops/frame_/tracker.py: Subclass Tracker of class Frame
################################################################################

import numpy as np
from polymath import *

from oops.frame_.frame import Frame
from oops.path_.path   import Path, AliasPath
from oops.transform    import Transform
from oops.event        import Event

class Tracker(Frame):
    """Tracker is a Frame subclass that ensures, via a small rotation, that a
    designated target path will stay in a fixed direction over a reasonably
    short time interval. ("Reasonably short" is defined by the requirement that
    the light travel time to the target not change significantly.)
    """

    def __init__(self, frame, target, observer, epoch, id=None):
        """Constructor for a Tracker Frame.

        Input:
            frame       the frame that will be modified to enable tracking. Must
                        be inertial.
            target      the name of the target path.
            observer    the name of the observer path.
            epoch       the epoch for which the given frame is defined.
            id          the ID to use; None to use a temporary ID.
        """

        self.fixed_frame = Frame.as_frame(frame)
        self.target_path = Path.as_path(target)
        self.observer_path = Path.as_path(observer)
        self.epoch = epoch

        assert self.fixed_frame.shape == ()
        assert self.target_path.shape == ()
        assert self.observer_path.shape == ()

        # Required attributes
        self.frame_id  = id or Frame.temporary_frame_id()
        self.reference = self.fixed_frame.reference
        self.origin    = self.fixed_frame.origin
        self.shape     = ()
        self.keys      = set()

        if id:
            self.register()
        else:
            self.wayframe = self

        obs_event = Event(epoch, (Vector3.ZERO,Vector3.ZERO),
                          self.observer_path, Frame.J2000)
        (path_event,obs_event) = self.target_path.photon_to_event(obs_event)
        self.trackpoint = -obs_event.arr.unit()

        fixed_xform = self.fixed_frame.transform_at_time(self.epoch)
        self.reference_xform = Transform(fixed_xform.matrix, Vector3.ZERO,
                                         self.wayframe, self.reference,
                                         self.origin)
        assert fixed_xform.omega == Vector3.ZERO

        # Convert the matrix to three axis vectors
        self.reference_rows = Vector3(self.reference_xform.matrix.values)

        # Prepare to cache the most recently used transform
        self.cached_time = None
        self.cached_xform = None
        dummy = self.transform_at_time(self.epoch)  # cache initialized

    ########################################

    def transform_at_time(self, time, quick=False):
        """The Transform into the this Frame at a Scalar of times."""

        if time == self.cached_time: return self.cached_xform

        # Determine the needed rotation
        obs_event = Event(time, (Vector3.ZERO,Vector3.ZERO),
                          self.observer_path, Frame.J2000)
        (path_event,obs_event) = self.target_path.photon_to_event(obs_event)
        newpoint = -obs_event.arr.unit()

        rotation = self.trackpoint.cross(newpoint)
        rotation = rotation.reshape(rotation.shape + (1,))

        # Rotate the three axis vectors accordingly
        new_rows = self.reference_rows.spin(rotation)
        xform = Transform(Matrix3(new_rows.vals),
                          Vector3.ZERO, # neglect the slow frame rotation
                          self.wayframe, self.reference, self.origin)

        # Cache the most recently used transform
        self.cached_time = time
        self.cached_xform = xform
        return xform

################################################################################
# UNIT TESTS
################################################################################

import unittest

class Test_Tracker(unittest.TestCase):

    def runTest(self):

        import oops.body as body
        import oops.spice_support as spice

        Path.reset_registry()
        Frame.reset_registry()

        body.define_solar_system("1999-01-01", "2002-01-01")

        tracker = Tracker("J2000", "MARS", "EARTH", 0., id="TEST")
        mars = AliasPath("MARS")

        obs_event = Event(0., (Vector3.ZERO,Vector3.ZERO), "EARTH", "J2000")
        (path_event, obs_event) = mars.photon_to_event(obs_event)
        start_arr = obs_event.arr.unit()

        # Track Mars for 30 days
        DAY = 86400
        for t in range(0,30*DAY,DAY):
            obs_event = Event(t, (Vector3.ZERO,Vector3.ZERO), "EARTH", "TEST")
            (path_event, obs_event) = mars.photon_to_event(obs_event)
            self.assertTrue(abs(obs_event.arr.unit() - start_arr) < 1.e-6)

        # Try the test all at once
        t = np.arange(0,30*DAY,DAY/40)
        obs_event = Event(t, (Vector3.ZERO,Vector3.ZERO), "EARTH", "TEST")
        (path_event, obs_event) = mars.photon_to_event(obs_event)
        self.assertTrue(abs(obs_event.arr.unit() - start_arr).max() < 1.e-6)

        Path.reset_registry()
        Frame.reset_registry()

#########################################
if __name__ == '__main__':
    unittest.main(verbosity=2)
################################################################################
