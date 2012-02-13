################################################################################
# oops/path/__init__.py: Abstract Path class and its required subclasses
################################################################################

import numpy as np

import oops.path.registry as registry
import oops.frame.registry as frame_registry
import oops.constants as constants

from oops.event import Event
from oops.xarray.all import *

class Path(object):
    """A Path is an abstract class that returns an Event (time, position and
    velocity) given a Scalar time. The coordinates are specified in a particular
    frame and relative to another path. All paths are ultimately references to
    the Solar System Barycenter ("SSB") and the J2000 coordinate frame."""

    DEBUG = False

########################################
# Each subclass must override...
########################################

    def __init__(self):
        """Constructor for a Path object. Every path must have these attributes:

        path_id         the ID of this Path, either a string or an integer.
        origin_id       the ID of the origin Path, relative to which this Path
                        is defined.
        frame_id        the ID of the frame used by the event objects returned.
        shape           the shape of this object, i.e, the shape of the event
                        returned when a single value of time is passed to
                        event_at_time().

        The primary definition of a path will be assigned this attribute by the
        registry:

        ancestry        a list of Path objects beginning with this one and
                        ending with with the Solar System Barycenter, where each
                        Path in sequence is the origin of the previous Path:
                            self.ancestry[0] = self.
                            self.ancestry[1] = origin path of self.
                            ...
                            self.ancestry[-1] = SSB in J2000.
        """

        pass

    def event_at_time(self, time):
        """Returns an Event object corresponding to a specified Scalar time on
        this path.

        Input:
            time        a time Scalar at which to evaluate the path.

        Return:         an event object containing (at least) the time, position
                        and velocity of the path.

        Note that the time and the path are not required to have the same shape;
        standard rules of broadcasting apply.
        """

        pass

########################################
# Override for enhanced performance
########################################

    def quick_path(self, epoch, span, precision=None, check=True):
        """Returns a new Path object that provides accurate approximations to
        the position and velocity vectors returned by this path. It is provided
        as a "hook" that can be used to speed up performance when the same path
        must be evaluated repeatedly but within a very narrow range of times.

        Input:
            epoch       the single time value about which this path will be
                        approximated.
            span        the range of times in seconds for which the approximated
                        Path object will operate: [epoch - span, epoch + span].
            precision   if provided, an upper limit on the positional precision
                        of the new Path object.
            check       if True, then an attempt to evaluate the path at a time
                        outside the allowed limits will raise a ValueError.
        """

        return self

################################################################################
# Registry Management
################################################################################

    # The global registry is keyed in two ways. If the key is a string, then
    # this constitutes the primary definition of the path. The origin_id
    # of the path must already be in the registry, and the new path's ID
    # cannot be in the registry.
    
    # We also create secondary definitions of a path, where it is defined
    # relative to a different reference frame and/or with respect to a different
    # origin. These are entered into the registry keyed twice, by a tuple:
    #   (path_id, origin_id)
    # and a triple:
    #   (path_id, origin_id, frame_id).
    # This saves the effort of re-creating paths used repeatedly.

    @staticmethod
    def initialize_registry():
        """Initializes the registry. It is not generally necessary to call this
        function, but it can be used to reset the registry for purposes of
        debugging."""

        global WAYPOINT_SUBCLASS

        if registry.SSB is None:
            registry.SSB = Waypoint("SSB")
            registry.SSB.ancestry = [registry.SSB]

        registry.REGISTRY = {"SSB": registry.SSB,
                             ("SSB","SSB"): registry.SSB,
                             ("SSB","SSB","J2000"): registry.SSB}

    def register(self, shortcut=None):
        """Registers a Path definition. If the path's ID is new, it is assumed
        to be the primary definition and is keyed by the ID alone. However, a
        primary definition must use an origin ID that is already registered.

        Otherwise or in addition, two secondary keys are added to the registry
        if they are not already present:
            (path_id, reference_id)
            (path_id, reference_id, frame_id)
        These keys also point to the same Path object.

        If a shortcut name is given, then self is treated as a shortcut
        definition. The path is registered under the shortcut name and also
        under the triplet (path_id, reference_id, frame_id), but other
        registered definitions of the path are not modified.
        """

        # Make sure the registry is initialized
        if registry.REGISTRY == {}: Path.initialize_registry()

        # Handle a shortcut
        if shortcut is not None:
            registry.REGISTRY[shortcut] = self
            registry.REGISTRY[(self.path_id, self.origin_id,
                                             self.frame_id)] = self
            return

        # Make sure the origin is registered
        origin = registry.REGISTRY[self.origin_id]

        # If the ID is unregistered, insert this as a primary definition
        try:
            test = registry.REGISTRY[self.path_id]
        except KeyError:
            registry.REGISTRY[self.path_id] = self

            # Fill in the ancestry too
            self.ancestry = [self] + origin.ancestry

            # Also define the "Waypoint" versions
            waypoint = Waypoint(self.path_id, self.frame_id)

            registry.REGISTRY[(self.path_id, self.path_id)] = waypoint
            registry.REGISTRY[(self.path_id, self.path_id,
                                             self.frame_id)] = waypoint

            # Also define the path with respect to the SSB if possible
            if self.origin_id != "SSB" or self.frame_id != "J2000":
              try:
                wrt_ssb = self.connect_to("SSB", "J2000")
                registry.REGISTRY[(wrt_ssb.path_id, "SSB", "J2000")] = wrt_ssb
                if (wrt_ssb.path_id, "SSB") not in registry.REGISTRY:
                    registry.REGISTRY[(wrt_ssb.path_id, "SSB")] = wrt_ssb
              except: pass

        # If the tuple (self.frame_id, self.origin_id) is unregistered, insert
        # this as a secondary definition
        key = (self.path_id, self.origin_id)
        try:
            test = registry.REGISTRY[key]
        except KeyError:
            registry.REGISTRY[key] = self

        # If the triple (self.frame_id, self.origin_id, self.frame_id) is
        # unregistered, insert this as a tertiary definition
        key = (self.path_id, self.origin_id, self.frame_id)
        try:
            test = registry.REGISTRY[key]
        except KeyError:
            registry.REGISTRY[key] = self

    def unregister(self):
        """Removes this path from the registry."""

        # Note that we only delete the primary entry and any path in which this
        # is one of the end points. If the path is used as an intermediate step
        # between other paths, it will cease to be visible in the dictionary
        # but paths that use it will continue to function unchange.

        path_id = self.path_id
        for key in registry.REGISTRY.keys():
            if path_id == key: del registry.REGISTRY[key]

            if type(key) == type(()):
                if path_id == key[0]: del registry.REGISTRY[key]
                if path_id == key[1]: del registry.REGISTRY[key]

    @staticmethod
    def unregister_frame(frame_id):
        """Removes any explicit reference to this frame from the path registry.
        It does not affect any paths that might use this frame internally."""

        # Note that we only delete the primary entry and any path in which this
        # is one of the end points. If the path is used as an intermediate step
        # between other paths, it will cease to be visible in the dictionary
        # but paths that use it will continue to function unchange. However, it
        # is safest to remove all usage of a frame at the time it is
        # unregistered.

        for key in registry.REGISTRY.keys():
            if type(key) == type(()) and len(key) > 2:
                if frame_id == key[2]: del registry.REGISTRY[key]

    def reregister(self):
        """Adds this frame to the registry, replacing any definition of the same
        name."""

        self.unregister()
        self.register()

    @staticmethod
    def lookup(key): return registry.REGISTRY[key]

################################################################################
# Event operations
################################################################################

# These must be defined here and not in Event.py, because that would create a
# circular dependency in the order that modules are loaded.

    def subtract_from_event(self, event):
        """Returns the same event, but with this path redefining its origin.

        Input:
            event       the event object from which this path is to be
                        subtracted. The path's origin must coincide with the
                        event's origin, and the two objects must use the same
                        frame.
        """

        # Check for compatibility
        assert self.origin_id == event.origin_id
        assert self.frame_id  == event.frame_id

        # Create a new event by subtracting this path from the origin
        offset = self.event_at_time(event.time)

        result = Event(event.time.copy(),
                       event.pos - offset.pos,
                       event.vel - offset.vel,
                       self.path_id, event.frame_id,
                       event.perp.copy(),
                       event.arr.copy(),
                       event.dep.copy(),
                       event.vflat.copy())

        result.ssb = event.ssb
        return result.update_shape()

    def add_to_event(self, event):
        """Returns the same event, but with the origin of this path redefining
        its origin.

        Input:
            event       the event object to which this path is to be added.
                        The path's endpoint must coincide with the event's
                        origin, and the two objects must use the same frame.
        """

        # Check for compatibility
        assert self.path_id  == event.origin_id
        assert self.frame_id == event.frame_id

        # Create a new event by subtracting this path from the origin
        offset = self.event_at_time(event.time)

        return Event(event.time,
                     event.pos + offset.pos,
                     event.vel + offset.vel,
                     self.origin_id, event.frame_id,
                     event.perp.copy(),
                     event.arr.copy(),
                     event.dep.copy(),
                     event.vflat.copy())

################################################################################
# Photon Solver
################################################################################

    def photon_from_event(self, event, iters=3, quick_info=None):
        """Returns a new event object corresponding to the arrival of a photon
        at this path, given that the same photon departed from the specified
        event at an earlier time.

        Input:
            event       the event of a photon's departure.

            iters       number of iterations of Newton's method to perform. For
                        iters == 0, the time of the returned event will only be
                        corrected for the light travel time to the path's
                        origin. Full precision is generally achieved in 2-3
                        iterations.

            quick_info  parameters to be passed to quick_path() and
                        quick_frame(), if these mechanisms are to be used to
                        speed up the calculations. None to do things the slow
                        way.

        Return:         a tuple containing(path_event, lt)

            path_event  the associated photon arrival or departure event on this
                        path. The shape comes from broadcasting the shapes of
                        the event and the path.

            lt          the light travel time between the two events.

        Side-Effects:   the photon departure attribute is filled in for the
                        event given.
        """

        return self._solve_photon(event, +1, iters, quick_info)

    def photon_to_event(self, event, iters=3, quick_info=None):
        """Returns a new event object corresponding to the departure of a photon
        from this path, given that the same photon arrived from the specified
        event at a later time. It also fills in the photon arrival direction
        attribute of the given event.

        Input:
            event       the event of a photon's arrival.

            iters       number of iterations of Newton's method to perform. For
                        iters == 0, the time of the returned event will only be
                        corrected for the light travel time to the path's
                        origin. Full precision is generally achieved in 2-3
                        iterations.

            quick_info  parameters to be passed to quick_path() and
                        quick_frame(), if these mechanisms are to be used to
                        speed up the calculations. None to do things the slow
                        way.

        Return:         a tuple containing(path_event, lt)

            path_event  the associated photon arrival or departure event on this
                        path. The shape comes from broadcasting the shapes of
                        the event and the path.

            lt          the light travel time between the two events.

        Side-Effects:   the photon arrival attribute is filled in for the event
                        given.
        """

        return self._solve_photon(event, -1, iters, quick_info)

    def _solve_photon(self, event, sign=-1, iters=3, quick_info=None):
        """Solve for a photon event on this path, given that the other end of
        the photon's path is at another specified event (time and position).

        Input:

            event       the Event of a photon's arrival or departure.

            sign        -1 to return earlier events, corresponding to photons
                           departing from the path and arriving at the event.
                        +1 to return later events, corresponding to photons
                           arriving at the path after departing from the event.

            iters       number of iterations of Newton's method to perform. For
                        iters == 0, the time of the returned event will only be
                        corrected for the light travel time to the path's
                        origin. Full precision is generally achieved in 2-3
                        iterations.

            quick_info  parameters to be passed to quick_path() and
                        quick_frame(), if these mechanisms are to be used to
                        speed up the calculations. None to do things the slow
                        way.

        Return:         a tuple containing(path_event, lt)

            path_event  the associated photon arrival or departure event on this
                        path. The shape comes from broadcasting the shapes of
                        the event and the path.

            lt          the light travel time between the two events.

        Side-Effects:   the photon's arrival or departure attribute is filled in
                        for the event.
        """

        # Iterate to a solution for the light travel time "lt". Define
        #   y = separation_distance(time + lt) - sign * c * lt
        # where lt is negative for earlier events and positive for later events.
        #
        # Solve for the value of lt at which y = 0, using Newton's method.
        #
        # Approximate the function as linear around the solution:
        #   y[n+1] - y[n] = (lt[n+1] - lt[n]) * dy_dlt
        # Our goal is for the next value of y, y[n+1], to equal zero. Our most
        # recent guess is (lt[n], y[n]).
        #
        # What should we use for lt[n+1]?
        #   lt[n+1] = lt[n] - y[n] / dy_dlt
        #
        # The function y is shown above. Its derivative is
        #   dy_dlt = outward_speed - sign * c

        signed_c = sign * constants.C

        # Define the path and event relative to the SSB in J2000
        path_wrt_ssb  = Path.connect(self, "SSB", "J2000")
        event_wrt_ssb = event.wrt_ssb()

        # Make an initial guess at the light travel time
        lt = (path_wrt_ssb.event_at_time(event.time).pos
              - event_wrt_ssb.pos).norm() / signed_c
        path_time = event.time + lt

        # Speed up the path and frame evaluations if requested
        if quick_info is not None:
            epoch = np.mean(path_time.vals)
            path_wrt_ssb = path_wrt_ssb.quick_path(epoch, quick_info)

        # Iterate a fixed number of times. Newton's method ensures that
        # convergence is quick
        for iter in range(iters):
            path_event = path_wrt_ssb.event_at_time(path_time)
            delta_pos = path_event.pos - event_wrt_ssb.pos
            delta_vel = path_event.vel - event_wrt_ssb.vel

            lt -= ((delta_pos.norm() - lt * signed_c) /
                   (delta_vel.proj(delta_pos).norm() - signed_c))

            path_time = event.time + lt

            if Path.DEBUG:
                print iter
                print ((delta_pos.norm() - lt * signed_c) /
                       (delta_vel.proj(delta_pos).norm() - signed_c))

        # Create the new event
        path_event_ssb = path_wrt_ssb.event_at_time(path_time)

        # Fill in the photon paths...

        # From path, to event
        if sign < 0:
            path_event_ssb.dep = event_wrt_ssb.pos - path_event_ssb.pos
            event_wrt_ssb.arr = path_event_ssb.dep

            event.ssb.arr = event_wrt_ssb.arr
            event.arr = event_wrt_ssb.wrt_frame(event.frame_id).arr

        # From event, to path
        else:
            path_event_ssb.arr = path_event_ssb.pos - event_wrt_ssb.pos
            event_wrt_ssb.dep = path_event_ssb.arr

            event.ssb.dep = event_wrt_ssb.dep
            event.dep = event_wrt_ssb.wrt_frame(event.frame_id).dep

        # Transform the absolute and relative events
        absolute_event = path_event_ssb.wrt(self.path_id, self.frame_id)
        absolute_event.ssb = path_event_ssb

        relative_event = path_event_ssb.wrt_event(event)
        relative_event = relative_event.wrt_frame(event.frame_id)
        relative_event.time = lt
        relative_event.ssb = path_event_ssb

        # Return the new event in two forms
        return (absolute_event, relative_event)

################################################################################
# Path Generators
################################################################################

    @staticmethod
    def connect(target, origin, frame="J2000"):
        """Returns a path that creates event objects in which vectors point
        from any origin path to any target path, using any coordinate frame.

        Input:
            target      the Path object or ID of the target path.
            origin      the Path object or ID of the origin path.
            frame       the Frame object of ID of the coordinate frame to use;
                        use None for the default frame of the origin.
        """

        # Convert to IDs
        target_id = registry.as_id(target)
        origin_id = registry.as_id(origin)

        if frame is None:
            frame_id = registry.as_path(origin).frame_id
        else:
            frame_id = frame_registry.as_id(frame)

        # If the path already exists, just return it
        try:
            return registry.REGISTRY[(target_id, origin_id, frame_id)]
        except KeyError: pass

        # If the path exists but the frame is wrong, return a rotated version
        try:
            newpath = registry.REGISTRY[(target_id, origin_id)]
            result = Rotated(newpath, frame_id)
            result.register()
            return result
        except KeyError: pass

        # Otherwise, construct it from the common ancestor...

        target_path = registry.REGISTRY[target_id]
        return target_path.connect_to(origin_id, frame_id)

    # Can be overridden by some classes such as SpicePath, where it is easier
    # to make connections.
    def connect_to(self, origin, frame=None):
        """Returns a Path object in which events point from an arbitrary origin
        path to this path.

        Input:
            origin          an origin Path object or its registered name.
            frame           a frame object or its registered ID. Default is
                            to use the frame of the origin's path.
        """

        # Get the endpoint paths and the frame
        target = registry.as_primary(self)
        origin = registry.as_primary(origin)

        if frame is None:
            frame_id = origin.frame_id
        else:
            frame_id = frame_registry.as_id(frame)

        # Find the common ancestry
        (target_ancestry,
         origin_ancestry) = Path.common_ancestry(target, origin)
        # print Path.str_ancestry((target_ancestry, origin_ancestry))

        # We can ignore the final (matching) entry in each list
        target_ancestry = target_ancestry[:-1]
        origin_ancestry = origin_ancestry[:-1]

        # Look up or construct the target's path from the common origin
        if target_ancestry == []:
            target_path = None
        elif len(target_ancestry) == 1:
            target_path = target
        else:
            try:
                target_path = registry.lookup((target.path_id,
                                               target_ancestry[-1].origin_id))
            except KeyError:
                target_path = Linked(target_ancestry)
                target_path.register()

        # Look up or construct the origin's path from the common ancestor
        if origin_ancestry == []:
            origin_path = None
        elif len(origin_ancestry) == 1:
            origin_path = origin
        else:
            try:
                origin_path = registry.lookup((origin.path_id,
                                               origin_ancestry[-1].origin_id))
            except KeyError:
                origin_path = Linked(origin_ancestry)
                origin_path.register()

        # Construct the relative path, irrespective of frame
        if origin_path is None:
            if target_path is None:
                result = Waypoint(self.path_id, frame_id)
            else:
                result = target_path
        else:
            if target_path is None:
                result = Reversed(origin_path)
            else:
                result = Relative(target_path, origin_path)

        result.register()

        # Rotate it into the proper frame if necessary
        if result.frame_id != frame_id:
            result = Rotated(result, frame_id)
            result.register()

        return result

    def common_ancestry(path1, path2):
        """Returns a pair of ancestry lists for the two given paths, where both
        lists end at Paths with the same name."""

        # Identify the first common ancestor of both paths
        for i in range(len(path1.ancestry)):
            id1 = path1.ancestry[i].path_id

            for j in range(len(path2.ancestry)):
                id2 = path2.ancestry[j].path_id

                if id1 == id2:
                    return (path1.ancestry[:i+1], path2.ancestry[:j+1])

        return (path1.ancestry, path2.ancestry)     # should never happen

    @staticmethod
    def str_ancestry(tuple):
        """Creates a string presenting the contents of the tuple containing the
        common ancestry between two paths. For debugging only."""

        list = ["(["]

        for item in tuple:
            for path in item:
                list += [path.path_id,"\", \""]

            list.pop()
            list += ["\"], [\""]

        list.pop()
        list += ["\"])"]

        return "".join(list)

########################################
# Arithmetic operators
########################################

    # unary "-" operator
    def __neg__(self):
        return path.Reversed(self)

    # binary "-" operator
    def __sub__(self, arg):

        if registry.is_id(arg) or isinstance(arg, Path):
            return Relative(self, arg)

        Array.raise_type_mismatch(self, "-", arg)

    # string operations
    def __str__(self):
        return ("Path([" + self.path_id   + " - " +
                           self.origin_id + "]/" +
                           self.frame_id + ")")

    def __repr__(self): return self.__str__()

################################################################################
# Define the required subclasses
################################################################################

class Linked(Path):
    """Linked is a Path subclass that links together a list of Path objects, so
    that the returned event points from the origin of the last frame to the
    endpoint of the first frame, and is given in the coordinates of the last
    frame. The origin_id of each list entry must be the path_id of the entry
    that follows.
    """

    def __init__(self, paths):
        """Constructor for a Linked Path.

        Input:
            paths       a list of connected paths. The origin_id of each path
                        must be the path_id of the one that follows.
        """

        self.paths = paths
        self.frames = []
        for i in range(len(paths)-1):
            self.frames += [frame_registry.connect(self.paths[i].frame_id,
                                                   self.paths[i+1].frame_id)]

        # Required fields
        self.path_id   = self.paths[0].path_id
        self.origin_id = self.paths[-1].origin_id
        self.frame_id  = self.paths[-1].frame_id
        self.shape     = Array.broadcast_shape(tuple(paths))

    def event_at_time(self, time):

        event = self.paths[0].event_at_time(time)
        for i in range(len(self.paths)-1):
            event = event.unrotate_by_frame(self.frames[i])
            event = self.paths[i+1].add_to_event(event)

        return event

################################################################################

class Relative(Path):
    """Relative is a Path subclass that returns the relative separation between
    two paths that share a common origin. The new path uses the coordinate frame
    of the origin path."""

    def __init__(self, path, origin):
        """Constructor for a RelativePath.

        Input:
            path        a Path object or ID defining the endpoint of the path
                        returned.
            origin      a Path object or ID defining the origin and frame of the
                        path returned.
        """

        self.path   = registry.as_path(path)
        self.origin = registry.as_path(origin)

        assert self.path.origin_id == self.origin.origin_id

        # Required fields
        self.path_id   = self.path.path_id
        self.origin_id = self.origin.path_id
        self.frame_id  = self.origin.frame_id
        self.shape     = Array.broadcast_shape((self.path, self.origin))

        self.path_frame = frame_registry.connect(self.path.frame_id,
                                                 self.origin.frame_id)

    def event_at_time(self, time):

        event = self.path.event_at_time(time).unrotate_by_frame(self.path_frame)

        event = self.origin.subtract_from_event(event)
        return event

################################################################################

class Reversed(Path):
    """Reversed is a subclass of Path that generates the reversed Events from
    that of a given Path."""

    def __init__(self, path):
        """Constructor for a ReversedPath.

        Input:
            path        the Path object to reverse, or its registered ID.
        """

        self.path = registry.as_path(path)

        # Required fields
        self.path_id   = self.path.origin_id
        self.origin_id = self.path.path_id
        self.frame_id  = self.path.frame_id
        self.shape     = self.path.shape

    def event_at_time(self, time):

        event = self.path.event_at_time(time)
        event.pos = -event.pos
        event.vel = -event.vel

        event.perp  = Empty()
        event.arr   = Empty()
        event.dep   = Empty()
        event.vflat = Vector3((0.,0.,0.))

        return event

################################################################################

class Rotated(Path):
    """Rotated is a Path subclass that returns event objects rotated to another
    coordinate frame."""

    def __init__(self, path, frame):
        """Constructor for a RotatedPath.

        Input:
            path        the Path object to rotate, or else its registered ID.
            frame       the Frame object by which to rotate the path, or else
                        its registered ID.
        """

        self.path = registry.as_path(path)
        newframe_id = frame_registry.as_id(frame)

        self.frame = frame_registry.connect(newframe_id, self.path.frame_id)

        # Required fields
        self.path_id   = self.path.path_id
        self.origin_id = self.path.origin_id
        self.frame_id  = newframe_id
        self.shape     = self.path.shape

    def event_at_time(self, time):

        return self.path.event_at_time(time).rotate_by_frame(self.frame)

################################################################################

class Waypoint(Path):
    """Waypoint is a Path subclass that always returns the origin."""

    def __init__(self, path_id, frame_id="J2000"):
        """Constructor for a Waypoint.

        Input:
            path_id     the path ID to use for both the origin and destination."
            frame_id    the frame ID to use.
        """

        # Required fields
        self.path_id   = path_id
        self.origin_id = path_id
        self.frame_id  = frame_id
        self.shape     = []

    def event_at_time(self, time):

        return Event.null_event(time, self.path_id, self.frame_id)

    def __str__(self):
        return "Waypoint(" + self.path_id + "/" + self.frame_id + ")"

################################################################################
# Initialize the registry
################################################################################

registry.PATH_CLASS = Path
Path.initialize_registry()

###############################################################################
# UNIT TESTS
################################################################################

import unittest

class Test_Path(unittest.TestCase):

    def runTest(self):

        # Imports are here to avoid conflicts
        from oops.frame.spiceframe import SpiceFrame
        from oops.path.spicepath import SpicePath

        # Registry tests
        registry.initialize_registry()
        frame_registry.initialize_registry()

        self.assertEquals(registry.REGISTRY["SSB"], registry.SSB)

        # Linked tests
        sun = SpicePath("SUN", "SSB")
        earth = SpicePath("EARTH", "SUN")
        moon = SpicePath("MOON", "EARTH")
        linked = Linked((moon, earth, sun))

        direct = SpicePath("MOON", "SSB")

        times = np.arange(-3.e8, 3.01e8, 0.5e7)

        direct_event = direct.event_at_time(times)
        linked_event = linked.event_at_time(times)

        eps = 1.e-6
        self.assertTrue(abs(linked_event.pos - direct_event.pos) <= eps)
        self.assertTrue(abs(linked_event.vel - direct_event.vel) <= eps)

        # Relative
        relative = Relative(linked, SpicePath("MARS", "SSB"))
        direct = SpicePath("MOON", "MARS")

        direct_event = direct.event_at_time(times)
        relative_event = relative.event_at_time(times)

        eps = 1.e-6
        self.assertTrue(abs(relative_event.pos - direct_event.pos) <= eps)
        self.assertTrue(abs(relative_event.vel - direct_event.vel) <= eps)

        # Reversed
        reversed = Reversed(relative)
        direct = SpicePath("MARS", "MOON")

        direct_event = direct.event_at_time(times)
        reversed_event = reversed.event_at_time(times)

        eps = 1.e-6
        self.assertTrue(abs(reversed_event.pos - direct_event.pos) <= eps)
        self.assertTrue(abs(reversed_event.vel - direct_event.vel) <= eps)

        # Rotated
        rotated = Rotated(reversed, SpiceFrame("B1950"))
        direct = SpicePath("MARS", "MOON", "B1950")

        direct_event = direct.event_at_time(times)
        rotated_event = rotated.event_at_time(times)

        eps = 1.e-6
        self.assertTrue(abs(rotated_event.pos - direct_event.pos) <= eps)
        self.assertTrue(abs(rotated_event.vel - direct_event.vel) <= eps)

        registry.initialize_registry()
        frame_registry.initialize_registry()

########################################
if __name__ == '__main__':
    unittest.main(verbosity=2)
################################################################################

################################################################################
if __name__ == '__main__':
    unittest.main(verbosity=2)
################################################################################