################################################################################
# oops/path/linearpath.py: Subclass LinearPath of class Path
################################################################################

import numpy as np
from polymath import Qube, Boolean, Scalar, Pair, Vector
from polymath import Vector3, Matrix3, Quaternion

from .       import Path
from ..event import Event
from ..frame import Frame

class LinearPath(Path):
    """A path defining linear motion relative to another path and frame."""

    # Note: LinearPaths are not generally re-used, so their IDs are expendable.
    # Their IDs are not preserved during pickling.

    #===========================================================================
    def __init__(self, pos, epoch, origin, frame=None, path_id=None):
        """Constructor for a LinearPath.

        Input:
            pos         a Vector3 of position vectors. The velocity should be
                        defined via a derivative 'd_dt'. Alternatively, it can
                        be specified as a tuple of two Vector3 objects,
                        (position, velocity).
            epoch       time Scalar relative to which the motion is defined,
                        seconds TDB
            origin      the path or path ID of the reference point.
            frame       the frame or frame ID of the coordinate system; None for
                        the frame used by the origin path.
            path_id     the name under which to register the new path; None to
                        leave the path unregistered.
        """

        # Interpret the position
        if isinstance(pos, (tuple,list)) and len(pos) == 2:
            self.pos = Vector3.as_vector3(pos[0]).wod.as_readonly()
            self.vel = Vector3.as_vector3(pos[1]).wod.as_readonly()
        else:
            pos = Vector3.as_vector3(pos)

            if hasattr('d_dt', pos):
                self.vel = pos.d_dt.as_readonly()
            else:
                self.vel = Vector3.ZERO

            self.pos = pos.wod.as_readonly()

        self.epoch = Scalar.as_scalar(epoch)

        # Required attributes
        self.path_id = path_id
        self.origin  = Path.as_waypoint(origin)
        self.frame   = Frame.as_wayframe(frame) or self.origin.frame
        self.keys    = set()
        self.shape   = Qube.broadcasted_shape(self.pos, self.vel,
                                              self.epoch,
                                              self.origin, self.frame)

        # Update waypoint and path_id; register only if necessary
        self.register()

    # Unpickled paths will always have temporary IDs to avoid conflicts
    def __getstate__(self):
        return (self.pos, self.epoch, self.origin, self.frame)

    def __setstate__(self, state):
        self.__init__(*state)

    #===========================================================================
    def event_at_time(self, time, quick=None):
        """An Event corresponding to a specified time on this path.

        Input:
            time        a time Scalar at which to evaluate the path.

        Return:         an Event object containing (at least) the time, position
                        and velocity on the path.
        """

        return Event(time, (self.pos + (time-self.epoch) * self.vel, self.vel),
                           self.origin, self.frame)

################################################################################
# UNIT TESTS
################################################################################

import unittest

class Test_LinearPath(unittest.TestCase):

    def runTest(self):

        # TBD
        pass

########################################
if __name__ == '__main__':
    unittest.main(verbosity=2)
################################################################################
