################################################################################
# oops_/backplane.py: Backplane class
#
# 3/14/12 Created (MRS)
# 3/24/12 MRS - Revised handling of keys into the backplane dictionary, added
#   support for ansa surfaces; an entirely masked backplane no longer causes
#   problems.
# 5/4/12 MRS - Updated ansa backplanes and added ansa longitude backplanes.
# 5/14/12 MRS - Added ring azimuth and elevation backplanes; introduced
#   "gridless" events and scalar quantitities, renamed "range" to "distance" to
#   avoid potential confusion with the Python "range" object; introduced
#   ring_emission_angle() and ring_incidence_angle() to support the standard
#   conventions for rings; set up faster/better evaluations of ring and ansa
#   longitudes.
# 6/6/12 MRS - Added limb geometry.
# 7/29/12 MRS - Revised the calling sequence to support observation subclasses
#   other than images.
# 8/19/12 MRS - Added where_not(), where_any() and where_all(), misc.
#   reorganization to support more path events, misc. bug fixes.
#
# TBD...
#   position(self, event_key, axis="x", apparent=True, frame="j2000")
#       returns an arbitrary position vector in an arbitrary frame
#   velocity(self, event_key, axis="x", apparent=True, frame="j2000")
#       returns an arbitrary velocity vector in an arbitrary frame
#   pole_clock_angle(self, event_key)
#       returns the projected angle of a body's pole vector on the sky
#   projected_radius(self, event_key, radius="long")
#       returns the projected angular radius of the body along its long or
#       short axis.
#   orbital_longitude(self, event_key, reference="j2000")
#       returns the orbital longitude of the body's path relative to the
#       barycenter of its motion.
################################################################################

import numpy as np
import oops_.config as config
import oops_.constants as constants
import oops_.registry as registry
import oops_.surface.all as surface_
import oops_.path.all as path_
from oops_.array.all import *
from oops_.event import Event
from oops_.meshgrid import Meshgrid

class Backplane(object):
    """Backplane is a class that supports the generation and manipulation of
    sets of backplanes associated with a particular observation. It caches
    intermediate results to speed up calculations."""

    HALFPI = np.pi / 2.
    TWOPI  = np.pi * 2.

    def __init__(self, obs, meshgrid=None, time=None):
        """The constructor.

        Input:
            obs         the Observation object with which this backplane is
                        associated.
            meshgrid    the optional meshgrid defining the sampling of the FOV.
                        Default is to sample the center of every pixel.
            time        a Scalar of times. The shape of this Scalar will be
                        broadcasted with the shape of the meshgrid. Default is
                        to sample the midtime of every pixel.
        """

        self.obs = obs

        if meshgrid is None and obs.fov is not None:
            swap = obs.u_axis > obs.v_axis or obs.u_axis == -1
            self.meshgrid = Meshgrid.for_fov(obs.fov, swap=swap)
        else:
            self.meshgrid = meshgrid

        self.obs_event = obs.event_at_grid(self.meshgrid, time)
        self.obs_gridless_event = obs.gridless_event(self.meshgrid, time)

        self.shape = self.obs_event.shape

        # The surface_events dictionary comes in two versions, one with
        # derivatives and one without. Each dictionary is keyed by a tuple of
        # strings, where each string is the name of a body from which photons
        # depart. Each event is defined by a call to Surface.photon_to_event()
        # to the next. The last event is the arrival at the observation, which
        # is implied so it does not appear in the key. For example, ("SATURN",)
        # is the key for an event defining the departures of photons from the
        # surface of Saturn to the observer. Shadow calculations require a
        # pair of steps; for example, ("saturn","saturn_main_rings") is the key
        # for the event of intercept points on Saturn that fall in the path of
        # the photons arriving at Saturn's rings from the Sun.
        #
        # Note that body names in event keys are case-insensitive.

        self.surface_events_w_derivs = {(): self.obs_event}
        self.surface_events = {(): self.obs_event.plain()}

        # The path_events dictionary holds photon departure events from paths.
        # All photons originate from the Sun so this name is implied. For
        # example, ("SATURN",) is the key for the event of a photon departing
        # the Sun such that it later arrives at the Saturn surface arrival
        # event.

        self.path_events = {}

        # The gridless_events dictionary keeps track of photon events at the
        # origin point of each defined surface. It uses the same keys as the
        # surface_events dictionary.

        self.gridless_events = {(): self.obs_gridless_event}

        # The backplanes dictionary holds every backplane that has been
        # calculated. This includes boolean backplanes, aka masks. A backplane
        # is keyed by (name of backplane, event_key, optional additional
        # parameters). The name of the backplane is always the name of the
        # backplane method that generates this backplane. For example,
        # ("phase_angle", ("saturn",)) is the key for a backplane of phase angle
        # values at the Saturn intercept points.
        #
        # If the function that returns a backplane requires additional
        # parameters, those appear in the tuple after the event key in the same
        # order that they appear in the calling function. For example,
        # ("latitude", ("saturn",), "graphic") is the key for the backplane of
        # planetographic latitudes at Saturn.

        self.backplanes = {}

    ############################################################################
    # Event manipulations
    #
    # Event keys are tuples (body_id, body_id, ...) where each body_id is a
    # a step along the path of a photon. The path always begins at the Sun and
    # and ends at the observer.
    ############################################################################

    @staticmethod
    def standardize_event_key(event_key):
        """Repairs the given event key to make it suitable as an index into the
        event dictionary. A string gets turned into a tuple."""

        if type(event_key) == type(""):
            return (event_key,)
        elif isinstance(event_key, basestring):
            return (str(event_key),)
        elif type(event_key) == type(()):
            return event_key
        else:
            raise ValueError("illegal event key type: " + str(type(event_key)))

    @staticmethod
    def standardize_backplane_key(backplane_key):
        """Repairs the given backplane key to make it suitable as an index into
        the backplane dictionary. A string is turned into a tuple. Strings are
        converted to lower case. If the argument is a backplane already, the key
        is extracted from it."""

        if type(backplane_key) == type(""):
            return (backplane_key.lower(),)
        elif type(backplane_key) == type(()):
            return backplane_key
        elif isinstance(backplane_key, Array):
            return backplane_key.key
        else:
            raise ValueError("illegal backplane key type: " +
                              str(type(backplane_key)))

    @staticmethod
    def get_surface(surface_id):
        """Interprets the string identifying the surface and returns the
        associated surface. The string is normally a registered body ID (case
        insensitive), but it can be modified with ":ansa", ":ring" or ":limb"
        to indicate an associated surface."""

        surface_id = surface_id.upper()

        modifier = None
        if surface_id.endswith(":ANSA"):
            modifier = "ANSA"
            body_id = surface_id[:-5]

        elif surface_id.endswith(":RING"):
            modifier = "RING"
            body_id = surface_id[:-5]

        elif surface_id.endswith(":LIMB"):
            modifier = "LIMB"
            body_id = surface_id[:-5]

        else:
            modifier = None
            body_id = surface_id

        body = registry.body_lookup(body_id)

        if modifier is None:
            return body.surface

        if modifier == "RING":
            return surface_.RingPlane(body.path_id, body.ring_frame_id,
                                      gravity=body.gravity)

        if modifier == "ANSA":
            if body.surface.COORDINATE_TYPE == "polar":     # if it's a ring
                return surface_.Ansa.for_ringplane(body.surface)
            else:                                           # if it's a planet
                return surface_.Ansa(body.path_id, body.ring_frame_id)

        if modifier == "LIMB":
            return surface_.Limb(body.surface, limits=(0.,np.inf))

    @staticmethod
    def get_path(path_id):
        """Interprets the string identifying the path and returns the
        associated path."""

        return registry.body_lookup(path_id.upper()).path

    def get_surface_event(self, event_key):
        """Returns the event of photons leaving the specified body surface and
        arriving at a destination event, as identified by its key."""

        event_key = Backplane.standardize_event_key(event_key)

        # If the event already exists, return it
        try:
            return self.surface_events[event_key]
        except KeyError: pass

        # The Sun is treated as a path, not a surface, unless it is first
        if event_key[0].upper() == "SUN" and len(event_key) >1:
            return self.get_path_event(event_key)

        # Look up the photon's departure surface and destination
        dest = self.get_surface_event(event_key[1:])
        surface = Backplane.get_surface(event_key[0])

        # Calculate derivatives for the first step from the observer, if allowed
        if len(event_key) == 1 and surface.intercept_DERIVS_ARE_IMPLEMENTED:
            try:
                ignore = self.get_surface_event_w_derivs(event_key)
                return self.surface_events[event_key]
            except NotImplementedError:
                pass

        # Create the event and save it in the dictionary
        event = surface.photon_to_event(dest)

        # Save extra information in the event object
        event.insert_subfield("event_key", event_key)
        event.insert_subfield("surface", surface)

        self.surface_events[event_key] = event
        return event

    def get_surface_event_w_derivs(self, event_key):
        """Returns the event of photons leaving the specified body surface and
        arriving at a destination event identified by its key. This version
        ensures that the surface derivatives are also included."""

        event_key = Backplane.standardize_event_key(event_key)

        # If the event already exists, return it
        try:
            return self.surface_events_w_derivs[event_key]
        except KeyError: pass

        # Create the event
        dest = self.get_surface_event(event_key[1:])
        surface = Backplane.get_surface(event_key[0])

        event = surface.photon_to_event(dest, derivs=True)

        # Save extra information in the event object
        event.insert_subfield("event_key", event_key)
        event.insert_subfield("surface", surface)

        self.surface_events_w_derivs[event_key] = event

        event_wo_derivs = event.plain()
        event_wo_derivs.event_key = event_key
        self.surface_events[event_key] = event_wo_derivs

        # Also save into the dictionary keyed by the string name alone
        # Saves the bother of typing parentheses and a comma when it's not
        # really necessary
        if len(event_key) == 1:
            self.surface_events_w_derivs[event_key[0]] = event
            self.surface_events[event_key[0]] = event_wo_derivs

        return event

    def get_path_event(self, event_key):
        """Returns the event of photons leaving the specified path and arriving
        at a destination event identified by its key."""

        event_key = Backplane.standardize_event_key(event_key)

        # If the event already exists, return it
        try:
            return self.path_events[event_key]
        except KeyError: pass

        # Create the event
        dest = self.get_surface_event(event_key[1:])
        path = Backplane.get_path(event_key[0])

        event = path.photon_to_event(dest)
        event.event_key = event_key

        self.path_events[event_key] = event

        # For a tuple of length 1, also register under the name string
        if len(event_key) == 1:
            self.path_events[event_key[0]] = event

        return event

    def get_surface_event_with_arr(self, event_key):
        """Returns the event object associated with the specified key, after
        ensuring that the arrival photons have been filled in."""

        event = self.get_surface_event(event_key)
        if event.arr == Empty():
            ignore = self.get_path_event(("sun",) + event_key)

        return event

    def get_gridless_event(self, event_key):
        """Returns the event of photons leaving the origin of the specified
        body surface and arriving at origin of the destination event, as
        as identified by its key."""

        event_key = Backplane.standardize_event_key(event_key)

        # If the event already exists, return it
        try:
            return self.gridless_events[event_key]
        except KeyError: pass

        # Create the event and save it in the dictionary
        dest = self.get_gridless_event(event_key[1:])
        surface = Backplane.get_surface(event_key[0])

        path = registry.as_path(surface.origin_id)
        event = path.photon_to_event(self.obs_gridless_event)
        event = event.wrt_frame(surface.frame_id)

        # Save extra information in the event object
        event.insert_subfield("event_key", event_key)
        event.insert_subfield("surface", surface)

        self.gridless_events[event_key] = event
        return event

    def get_gridless_event_with_arr(self, event_key):
        """Returns the gridless event object associated with the specified key,
        after ensuring that the arrival photons have been filled in."""

        event_key = Backplane.standardize_event_key(event_key)

        event = self.get_gridless_event(event_key)
        if event.arr == Empty():
            ignore = path_.Waypoint("SUN").photon_to_event(event)

        return event

    def mask_as_scalar(self, mask):
        """Converts a mask represented by a single boolean into a boolean array.
        """

        if isinstance(mask, np.ndarray): return Scalar(mask)
        if mask:
            return Scalar(np.ones(self.meshgrid.shape, dtype="bool"))
        else:
            return Scalar(np.zeros(self.meshgrid.shape, dtype="bool"))

    def register_backplane(self, key, backplane):
        """Inserts this backplane into the dictionary. If the backplane contains
        just a single value, it is expanded to the overall shape of the
        backplane."""

        if isinstance(backplane, np.ndarray):
            backplane = Scalar(backplane)

        # Under some circumstances a derived backplane can be a scalar
        if backplane.shape == [] and self.shape != []:
            vals = np.empty(self.shape)
            vals[...] = backplane.vals
            backplane = Scalar(vals, backplane.mask)

        # For reference, we add the key as an attribute of each backplane object
        backplane = backplane.plain()
        backplane.key = key

        self.backplanes[key] = backplane

    def register_gridless_backplane(self, key, backplane):
        """Inserts this backplane into the dictionary. Same as
        register_backplane() but without the expansion of a scalar value."""

        if isinstance(backplane, np.ndarray):
            backplane = Scalar(backplane)

        # For reference, we add the key as an attribute of each backplane object
        backplane = backplane.plain()
        backplane.key = key

        self.backplanes[key] = backplane

    ############################################################################
    # Sky geometry, surface intercept versions
    #   right_ascension()       right ascension of field of view, radians.
    #   declination()           declination of field of view, radians.
    ############################################################################

    def right_ascension(self, event_key=(), apparent=True, direction="arr"):
        """Right ascension of the arriving or departing photon, optionally
        allowing for stellar aberration.

        Input:
            event_key       key defining the surface event, typically () to
                            refer to the observation.
            apparent        True to return the apparent direction of photons in
                            the frame of the event; False to return the purely
                            geometric directions of the photons.
            direction       "arr" to return the direction of an arriving photon;
                            "dep" to return the direction of a departing photon.
        """

        event_key = Backplane.standardize_event_key(event_key)

        key = ("right_ascension", event_key, apparent, direction)
        if key not in self.backplanes.keys():
            self._fill_ra_dec(event_key, apparent, direction)

        return self.backplanes[key]

    def declination(self, event_key=(), apparent=True, direction="arr"):
        """Declination of the arriving or departing photon, optionally
        allowing for stellar aberration.

        Input:
            event_key       key defining the surface event, typically () to
                            refer to the observation.
            apparent        True to return the apparent direction of photons in
                            the frame of the event; False to return the purely
                            geometric directions of the photons.
            direction       "arr" to base the direction on an arriving photon;
                            "dep" to base the direction on a departing photon.
        """

        event_key = Backplane.standardize_event_key(event_key)

        key = ("declination", event_key, apparent, direction)
        if key not in self.backplanes.keys():
            self._fill_ra_dec(event_key, apparent, direction)

        return self.backplanes[key]

    def _fill_ra_dec(self, event_key, apparent, direction):
        """Internal method to fill in right ascension and declination
        backplanes based on the meshgrid."""

        assert direction in ("arr", "dep")

        event = self.get_surface_event_with_arr(event_key)
        (ra, dec) = event.ra_and_dec(apparent, direction)

        self.register_backplane(("right_ascension", event_key,
                                apparent, direction), ra)
        self.register_backplane(("declination", event_key,
                                apparent, direction), dec)

    ############################################################################
    # Sky geometry, path intercept versions
    #   center_right_ascension()    right ascension of path on sky, radians.
    #   center_declination()        declination of path on sky, radians.
    ############################################################################

    def center_right_ascension(self, event_key, apparent=True, direction="arr"):
        """Right ascension of the arriving or departing photon, optionally
        allowing for stellar aberration and for frames other than J2000.

        Input:
            event_key       key defining the event at the body's path.
            apparent        True to return the apparent direction of photons in
                            the frame of the event; False to return the purely
                            geometric directions of the photons.
            direction       "arr" to return the direction of an arriving photon;
                            "dep" to return the direction of a departing photon.
        """

        event_key = Backplane.standardize_event_key(event_key)

        key = ("center_right_ascension", event_key, apparent, direction)
        if key not in self.backplanes.keys():
            self._fill_center_ra_dec(event_key, apparent, direction)

        return self.backplanes[key]

    def center_declination(self, event_key, apparent=True, direction="arr"):
        """Declination of the arriving or departing photon, optionally
        allowing for stellar aberration and for frames other than J2000.

        Input:
            event_key       key defining the event at the body's path.
            apparent        True to return the apparent direction of photons in
                            the frame of the event; False to return the purely
                            geometric directions of the photons.
            direction       "arr" to return the direction of an arriving photon;
                            "dep" to return the direction of a departing photon.
        """

        event_key = Backplane.standardize_event_key(event_key)

        key = ("center_declination", event_key, apparent, direction)
        if key not in self.backplanes.keys():
            self._fill_center_ra_dec(event_key, apparent, direction)

        return self.backplanes[key]

    def _fill_center_ra_dec(self, event_key, apparent, direction):
        """Internal method to fill in right ascension and declination
        backplanes based on the center of a body's path."""

        assert direction in ("arr", "dep")

        event = self.get_surface_event_with_arr(event_key)
        (ra, dec) = event.ra_and_dec(apparent, direction)

        self.register_gridless_backplane(
                ("center_right_ascension", event_key, apparent, direction), ra)
        self.register_gridless_backplane(
                ("center_declination", event_key, apparent, direction), dec)

    ############################################################################
    # Basic body geometry, surface intercept versions
    #   distance()          distance traveled by photon, km.
    #   light_time()        elapsed time from photon departure to arrival, sec.
    #   resolution()        resolution based on surface distance, as a quantity
    #                       defined perpendicular to the lines of sight, in
    #                       km/pixel.
    ############################################################################

    def distance(self, event_key, direction="dep"):
        """Range in km between a photon event and its counterpart at the surface
        of a body.

        Input:
            event_key       key defining the surface event.
            direction       "arr" for distance traveled by the arriving photon;
                            "dep" for distance traveled by the departing photon.
        """

        event_key = Backplane.standardize_event_key(event_key)
        assert direction in ("dep", "arr")

        key = ("distance", event_key, direction)
        if key not in self.backplanes.keys():
            lt = self.light_time(event_key, direction)
            self.register_backplane(key, lt * constants.C)

        return self.backplanes[key]

    def light_time(self, event_key, direction="dep"):
        """Time in seconds between a photon's arrival and its departure.

        Input:
            event_key       key defining the surface event.
            direction       "arr" for the travel time of the arriving photon;
                            "dep" for the travel time of the departing photon.
        """

        event_key = Backplane.standardize_event_key(event_key)
        assert direction in ("dep", "arr")

        key = ("light_time", event_key, direction)
        if key not in self.backplanes.keys():
            if direction == "arr":
                event = self.get_surface_event_with_arr(event_key)
            else:
                event = self.get_surface_event(event_key)

            lt = event.subfields[direction + "_lt"]
            self.register_backplane(key, abs(lt))

        return self.backplanes[key]

    def event_time(self, event_key):
        """The absolute time in seconds TDB when the photon intercepted the
        surface.

        Input:
            event_key       key defining the surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)

        key = ("event_time", event_key)
        if key not in self.backplanes.keys():
            event = self.get_surface_event(event_key)
            self.register_backplane(key, event.time)

        return self.backplanes[key]

    def resolution(self, event_key, axis="u"):
        """Projected spatial resolution in km/pixel at the surface intercept,
        defined perpendicular to the line of sight.

        Input:
            event_key       key defining the surface event.
            axis            "u" for resolution along the horizontal axis of the
                                observation;
                            "v" for resolution along the vertical axis of the
                                observation.
        """

        event_key = Backplane.standardize_event_key(event_key)
        assert axis in ("u","v")

        key = ("resolution", event_key, axis)
        if key not in self.backplanes.keys():
            distance = self.distance(event_key)

            (dlos_du, dlos_dv) = self.meshgrid.dlos_duv.as_columns()
            u_resolution = distance * dlos_du.as_vector3().norm()
            v_resolution = distance * dlos_dv.as_vector3().norm()

            self.register_backplane(key[:-1] + ("u",), u_resolution)
            self.register_backplane(key[:-1] + ("v",), v_resolution)

        return self.backplanes[key]

    ############################################################################
    # Basic body, path intercept versions
    #   center_distance()   distance traveled by photon, km.
    #   center_light_time() elapsed time from photon departure to arrival, sec.
    #   center_resolution() resolution based on body center distance, km/pixel.
    ############################################################################

    def center_distance(self, event_key, direction="obs"):
        """Range in km between a photon event and its counterpart at the
        central path of a body.

        Input:
            event_key       key defining the event at the body's path.
            direction       "arr" or "sun" to return the distance traveled by an
                                           arriving photon;
                            "dep" or "obs" to return the distance traveled by a
                                           departing photon.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("center_distance", event_key, direction)
        if key not in self.backplanes.keys():
            lt = self.center_light_time(event_key, direction)
            self.register_gridless_backplane(key, lt * constants.C)

        return self.backplanes[key]

    def center_light_time(self, event_key, direction="dep"):
        """Time in seconds between a photon event and its counterpert at the
        central path of a body.

        Input:
            event_key       key defining the event at the body's path.
            direction       "arr" or "sun" to return the travel time for an
                                           arriving photon;
                            "dep" or "obs" to return the travel time for a
                                           departing photon.
        """

        event_key = Backplane.standardize_event_key(event_key)
        assert direction in ("obs", "sun", "dep", "arr")

        key = ("center_light_time", event_key, direction)
        if key not in self.backplanes.keys():
            if direction in ("sun", "arr"):
                event = self.get_gridless_event_with_arr(event_key)
                lt = event.arr_lt
            else:
                event = self.get_gridless_event(event_key)
                lt = event.dep_lt

            self.register_gridless_backplane(key, abs(lt))

        return self.backplanes[key]

    def center_time(self, event_key):
        """The absolute time in seconds TDB when the photon intercepted the
        path.

        Input:
            event_key       key defining the event at the body's path.
        """

        event_key = Backplane.standardize_event_key(event_key)

        key = ("center_time", event_key)
        if key not in self.backplanes.keys():
            event = self.get_gridless_event(event_key)
            self.register_gridless_backplane(key, event.time)

        return self.backplanes[key]

    def center_resolution(self, event_key, axis="u"):
        """Directionless projected spatial resolution in km/pixel at the
        central path of a body, based on range alone.

        Input:
            event_key       key defining the event at the body's path.
            axis            "u" for resolution along the horizontal axis of the
                                observation;
                            "v" for resolution along the vertical axis of the
                                observation.
        """

        event_key = Backplane.standardize_event_key(event_key)
        assert axis in ("u","v")

        key = ("center_resolution", event_key, axis)
        if key not in self.backplanes.keys():
            distance = self.center_distance(event_key)

            (dlos_du, dlos_dv) = self.obs.fov.center_dlos_duv.as_columns()
            u_resolution = distance * dlos_du.as_vector3().norm()
            v_resolution = distance * dlos_dv.as_vector3().norm()

            self.register_gridless_backplane(key[:-1] + ("u",), u_resolution)
            self.register_gridless_backplane(key[:-1] + ("v",), v_resolution)

        return self.backplanes[key]

    ############################################################################
    # Lighting geometry, surface intercept version
    #   incidence_angle()   incidence angle at surface, radians.
    #   emission_angle()    emission angle at surface, radians.
    #   lambert_law()       Lambert Law model for surface, cos(incidence).
    ############################################################################

    def incidence_angle(self, event_key):
        """Incidence angle of the arriving photons at the local surface.

        Input:
            event_key       key defining the surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("incidence_angle", event_key)
        if key not in self.backplanes.keys():
            event = self.get_surface_event_with_arr(event_key)
            incidence = event.incidence_angle()

            # Ring incidence angles are always 0-90 degrees
            if event.surface.COORDINATE_TYPE == "polar":

                # flip is True wherever incidence angle has to be changed
                flip = (incidence > Backplane.HALFPI)
                self.register_backplane(("ring_flip", event_key), flip)

                # Now flip incidence angles where necessary
                incidence = np.pi * flip + (1. - 2.*flip) * incidence

            self.register_backplane(key, incidence)

        return self.backplanes[key]

    def emission_angle(self, event_key):
        """Emission angle of the departing photons at the local surface.

        Input:
            event_key       key defining the surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("emission_angle", event_key)
        if key not in self.backplanes.keys():
            event = self.get_surface_event(event_key)
            emission = event.emission_angle()

            # Ring emission angles are always measured from the lit side normal
            if event.surface.COORDINATE_TYPE == "polar":

                # Get the flip flag
                ignore = self.incidence_angle(event_key)
                flip = self.backplanes[("ring_flip", event_key)]

                # Flip emission angles where necessary
                emission = np.pi * flip + (1. - 2.*flip) * emission

            self.register_backplane(key, emission)

        return self.backplanes[key]

    def phase_angle(self, event_key):
        """Phase angle between the arriving and departing photons.

        Input:
            event_key       key defining the surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("phase_angle", event_key)
        if key not in self.backplanes.keys():
            event = self.get_surface_event_with_arr(event_key)
            self.register_backplane(key, event.phase_angle())

        return self.backplanes[key]

    def scattering_angle(self, event_key):
        """Scattering angle between the arriving and departing photons.

        Input:
            event_key       key defining the surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("scattering_angle", event_key)
        if key not in self.backplanes.keys():
            self.register_backplane(key, np.pi - self.phase_angle(event_key))

        return self.backplanes[key]

    def lambert_law(self, event_key):
        """Lambert law model cos(incidence_angle) for the surface.

        Input:
            event_key       key defining the surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("lambert_law", event_key)
        if key not in self.backplanes.keys():
            incidence = self.incidence_angle(event_key)
            lambert_law = incidence.cos()
            lambert_law.mask |= (incidence.vals >= Backplane.HALFPI)
            lambert_law.vals[lambert_law.mask] = 0.
            self.register_backplane(key, lambert_law)

        return self.backplanes[key]

    ############################################################################
    # Lighting geometry, path intercept version
    #   center_incidence_angle()    incidence angle at path, radians. This uses
    #                               the z-axis of the target frame to define the
    #                               normal vector; it is used primarily for
    #                               rings.
    #   center_emission_angle()     emission angle at surface, radians. See
    #                               above.
    #   center_phase_angle()        phase angle at body's center, radians.
    #   center_scattering_angle()   scattering angle at body's center, radians.
    ############################################################################

    def center_incidence_angle(self, event_key):
        """Incidence angle of the arriving photons at the body's central path.
        This uses the z-axis of the body's frame to define the local normal.

        Input:
            event_key       key defining the event on the body's path.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("center_incidence_angle", event_key)
        if key not in self.backplanes.keys():
            event = self.get_gridless_event_with_arr(event_key)

            # Sign on event.arr is negative because photon is incoming
            latitude = (-event.arr.as_scalar(2) / event.arr.norm()).arcsin()
            incidence = Backplane.HALFPI - latitude

            # Ring incidence angles are always 0-90 degrees
            if event.surface.COORDINATE_TYPE == "polar":

                # The flip is True wherever incidence angle has to be changed
                flip = (incidence > Backplane.HALFPI)
                self.register_gridless_backplane(("ring_center_flip",
                                                  event_key), flip)

                # Now flip incidence angles where necessary
                if flip.sum() > 0:
                    incidence = np.pi * flip + (1. - 2.*flip) * incidence

            self.register_gridless_backplane(key, incidence)

        return self.backplanes[key]

    def center_emission_angle(self, event_key):
        """Emission angle of the departing photons at the body's central path.
        This uses the z-axis of the body's frame to define the local normal.

        Input:
            event_key       key defining the event on the body's path.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("center_emission_angle", event_key)
        if key not in self.backplanes.keys():
            event = self.get_gridless_event(event_key)

            latitude = (event.dep.as_scalar(2) / event.dep.norm()).arcsin()
            emission = Backplane.HALFPI - latitude

            # Ring emission angles are always measured from the lit side normal
            if event.surface.COORDINATE_TYPE == "polar":

                # Get the flip flag
                ignore = self.center_incidence_angle(event_key)
                flip = self.backplanes[("ring_center_flip", event_key)]

                # Flip emission angles where necessary
                if flip.sum() > 0:
                    emission = np.pi * flip + (1. - 2.*flip) * emission

            self.register_gridless_backplane(key, emission)

        return self.backplanes[key]

    def center_phase_angle(self, event_key):
        """Phase angle as measured at the body's central path.

        Input:
            event_key       key defining the event on the body's path.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("center_phase_angle", event_key)
        if key not in self.backplanes.keys():
            event = self.get_gridless_event_with_arr(event_key)
            self.register_gridless_backplane(key, event.phase_angle())

        return self.backplanes[key]

    def center_scattering_angle(self, event_key):
        """Scattering angle as measured at the body's central path.

        Input:
            event_key       key defining the event on the body's path.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("center_scattering_angle", event_key)
        if key not in self.backplanes.keys():
            angle = np.pi - self.center_phase_angle(event_key)
            self.register_gridless_backplane(key, angle)

        return self.backplanes[key]

    ############################################################################
    # Body surface geometry, surface intercept versions
    #   longitude()
    #   latitude()
    ############################################################################

    def longitude(self, event_key, reference="iau", direction="west",
                                                    minimum=0):
        """Longitude at the surface intercept point in the image.

        Input:
            event_key       key defining the ring surface event.
            reference       defines the location of zero longitude.
                            "iau" for the IAU-defined prime meridian;
                            "obs" for the sub-observer longitude;
                            "sun" for the sub-solar longitude;
                            "oha" for the anti-observer longitude;
                            "sha" for the anti-solar longitude, returning the
                                  local time on the planet if direction is west.
            direction       direction on the surface of increasing longitude,
                            "east" or "west".
            minimum         the smallest numeric value of longitude, either 0
                            or -180.
        """

        event_key = Backplane.standardize_event_key(event_key)
        assert reference in ("iau", "sun", "sha", "obs", "oha")
        assert direction in ("east", "west")
        assert minimum in (0, -180)

        # Look up under the desired reference
        key0 = ("longitude", event_key)
        key = key0 + (reference, direction, minimum)
        if key in self.backplanes.keys():
            return self.backplanes[key]

        # If it is not found with default keys, fill in those backplanes
        # Note that longitudes default to eastward for right-handed coordinates
        key_default = key0 + ("iau", "east", 0)
        if key_default not in self.backplanes.keys():
            self._fill_surface_intercepts(event_key)

        # Fill in the values for this key
        if reference == "iau":
            ref_lon = 0.
        elif reference == "sun":
            ref_lon = self.sub_solar_longitude(event_key)
        elif reference == "sha":
            ref_lon = self.sub_solar_longitude(event_key) - np.pi
        elif reference == "obs":
            ref_lon = self.sub_observer_longitude(event_key)
        elif reference == "oha":
            ref_lon = self.sub_observer_longitude(event_key) - np.pi

        lon = self.backplanes[key_default] - ref_lon

        if direction == "west": lon = -lon

        if minimum == 0:
            lon = lon % Backplane.TWOPI
        else:
            lon = (lon + np.pi) % Backplane.TWOPI - np.pi

        self.register_backplane(key, lon)
        return self.backplanes[key]

    def latitude(self, event_key, lat_type="centric"):
        """Latitude at the surface intercept point in the image.

        Input:
            event_key       key defining the ring surface event.
            lat_type        defines the type of latitude measurement:
                            "centric"   for planetocentric;
                            "graphic"   for planetographic;
                            "squashed"  for an intermediate latitude type used
                                        internally.
        """

        event_key = Backplane.standardize_event_key(event_key)
        assert lat_type in ("centric", "graphic", "squashed")

        # Look up under the desired reference
        key0 = ("latitude", event_key)
        key = key0 + (lat_type,)
        if key in self.backplanes.keys():
            return self.backplanes[key]

        # If it is not found with default keys, fill in those backplanes
        key_default = key0 + ("squashed",)
        if key_default not in self.backplanes.keys():
            self._fill_surface_intercepts(event_key)

        # Fill in the values for this key
        lat = self.backplanes[key_default]
        if lat_type == "squashed":
            return lat

        event = self.get_surface_event(event_key)
        assert event.surface.COORDINATE_TYPE in ("spherical", "limb")

        if lat_type == "centric":
            lat = event.surface.lat_to_centric(lat)
        else:
            lat = event.surface.lat_to_graphic(lat)

        self.register_backplane(key, lat)
        return self.backplanes[key]

    def _fill_surface_intercepts(self, event_key):
        """Internal method to fill in the surface intercept geometry backplanes.
        """

        # Get the surface intercept coordinates
        event_key = Backplane.standardize_event_key(event_key)
        event = self.get_surface_event(event_key)

        # If this is actually a limb event, define the limb backplanes instead
        if event.surface.COORDINATE_TYPE == "limb":
            self._fill_limb_intercepts(event_key)
            return

        assert event.surface.COORDINATE_TYPE == "spherical"

        (lon,lat) = event.surface.event_as_coords(event, axes=2, derivs=False)

        self.register_backplane(("longitude", event_key, "iau", "east", 0), lon)
        self.register_backplane(("latitude", event_key, "squashed"), lat)

    ############################################################################
    # Surface geometry, path intercept versions
    #   sub_longitude()
    #   sub_solar_longitude()
    #   sub_observer_longitude()
    #   sub_latitude()
    #   sub_solar_latitude()
    #   sub_observer_latitude()
    ############################################################################

    def sub_longitude(self, event_key, reference="obs", direction="east"):
        """Sub-solar or sub-observer longitude at the body's path, relative
        to the x-coordinate of the body's coordinate frame. This is the IAU
        meridian for planets and moons, and the J2000 ascending node for rings.

        Input:
            event_key       key defining the event on the body's path.
            reference       "obs" for the sub-observer longitude;
                            "sun" for the sub-solar longitude.
            direction       the direction of increasing longitude, either "east"
                            or "west".
        """

        assert reference in ("obs", "sun")

        if reference == "obs":
            lon = self.sub_observer_longitude(event_key)
        else:
            lon = self.sub_solar_longitude(event_key)

        if direction == "west":
            lon = Backplane.TWOPI - lon

        return lon

    def sub_solar_longitude(self, event_key):
        """Sub-solar longitude, primarily used internally. Longitudes are
        measured eastward from the x-axis of the target's coordinate frame.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("sub_solar_longitude", event_key)

        if key not in self.backplanes.keys():
            event = self.get_gridless_event_with_arr(event_key)
            arr = -event.aberrated_arr()
            lon = arr.as_scalar(1).arctan2(arr.as_scalar(0)) % Backplane.TWOPI

            self.register_gridless_backplane(key, lon)

        return self.backplanes[key]

    def sub_observer_longitude(self, event_key):
        """Sub-observer longitude, primarily used internally. Longitudes are
        measured eastward from the x-axis of the target's coordinate frame.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("sub_observer_longitude", event_key)

        if key not in self.backplanes.keys():
            event = self.get_gridless_event(event_key)
            dep = event.aberrated_dep()
            lon = dep.as_scalar(1).arctan2(dep.as_scalar(0)) % Backplane.TWOPI

            self.register_gridless_backplane(key, lon)

        return self.backplanes[key]

    def sub_latitude(self, event_key, reference="obs", lat_type="centric"):
        """Sub-solar or sub-observer latitude at the body's path.

        Input:
            event_key       key defining the event on the body's path.
            reference       "obs" for the sub-observer latitude;
                            "sun" for the sub-solar latitude.
            lat_type        "centric" for planetocentric latitude;
                            "graphic" for planetographic latitude.
        """

        assert reference in ("obs", "sun")

        if reference == "obs":
            return self.sub_observer_latitude(event_key, lat_type)
        else:
            return self.sub_solar_latitude(event_key, lat_type)

    def sub_solar_latitude(self, event_key, lat_type="centric"):
        """Sub-solar latitude, primarily used internally."""

        event_key = Backplane.standardize_event_key(event_key)
        assert lat_type in ("centric", "graphic")

        key = ("sub_solar_latitude", event_key, lat_type)
        if key not in self.backplanes.keys():
            event = self.get_gridless_event_with_arr(event_key)
            arr = -event.aberrated_arr()

            if lat_type == "graphic":
                arr = arr * event.surface.unsquash_sq

            lat = (arr.as_scalar(2) / arr.norm()).arcsin()
            self.register_gridless_backplane(key, lat)

        return self.backplanes[key]

    def sub_observer_latitude(self, event_key, lat_type="centric"):
        """Sub-observer latitude, primarily used internally."""

        event_key = Backplane.standardize_event_key(event_key)
        assert lat_type in ("centric", "graphic")

        key = ("sub_observer_latitude", event_key, lat_type)
        if key not in self.backplanes.keys():
            event = self.get_gridless_event(event_key)
            dep = event.aberrated_dep()

            if lat_type == "graphic":
                dep = dep * event.surface.unsquash_sq

            lat = (dep.as_scalar(2) / dep.norm()).arcsin()
            self.register_gridless_backplane(key, lat)

        return self.backplanes[key]

    ############################################################################
    # Surface resolution, surface intercepts only
    #   finest_resolution()
    #   coarsest_resolution()
    ############################################################################

    def finest_resolution(self, event_key):
        """Projected spatial resolution in km/pixel in the optimal direction at
        the intercept point.

        Input:
            event_key       key defining the ring surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("finest_resolution", event_key)
        if key not in self.backplanes.keys():
            self._fill_surface_resolution(event_key)

        return self.backplanes[key]

    def coarsest_resolution(self, event_key):
        """Projected spatial resolution in km/pixel in the worst direction at
        the intercept point.

        Input:
            event_key       key defining the ring surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("coarsest_resolution", event_key)
        if key not in self.backplanes.keys():
            self._fill_surface_resolution(event_key)

        return self.backplanes[key]

    def _fill_surface_resolution(self, event_key):
        """Internal method to fill in the surface resolution backplanes.
        """

        event_key = Backplane.standardize_event_key(event_key)
        event = self.get_surface_event_w_derivs(event_key)

        dpos_duv = event.pos.d_dlos * self.meshgrid.dlos_duv
        (minres, maxres) = surface_.Surface.resolution(dpos_duv)

        self.register_backplane(("finest_resolution", event_key), minres)
        self.register_backplane(("coarsest_resolution", event_key), maxres)

    ############################################################################
    # Limb geometry, surface intercepts only
    #   altitude()
    ############################################################################

    def altitude(self, event_key):
        """Elevation of a limb point above the body's surface.

        Input:
            event_key       key defining the ring surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("altitude", event_key)
        if key not in self.backplanes.keys():
            self._fill_limb_intercepts(event_key)

        return self.backplanes[key]

    def _fill_limb_intercepts(self, event_key):
        """Internal method to fill in the limb intercept geometry backplanes.
        """

        # Get the limb intercept coordinates
        event_key = Backplane.standardize_event_key(event_key)
        event = self.get_surface_event(event_key)
        assert event.surface.COORDINATE_TYPE == "limb"

        (lon,lat,z) = event.surface.event_as_coords(event, axes=3)

        self.register_backplane(("longitude", event_key, "iau", "east", 0), lon)
        self.register_backplane(("latitude", event_key, "squashed"), lat)
        self.register_backplane(("altitude", event_key), z)

    ############################################################################
    # Ring plane geometry, surface intercept version
    #   ring_radius()
    #   ring_longitude()
    #   ring_azimuth()
    #   ring_elevation()
    ############################################################################

    def ring_radius(self, event_key):
        """Radius of the ring intercept point in the observation.

        Input:
            event_key       key defining the ring surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("ring_radius", event_key)
        if key not in self.backplanes.keys():
            self._fill_ring_intercepts(event_key)

        return self.backplanes[key]

    def ring_longitude(self, event_key, reference="j2000"):
        """Longitude of the ring intercept point in the image.

        Input:
            event_key       key defining the ring surface event.
            reference       defines the location of zero longitude.
                            "j2000" for the J2000 ascending node;
                            "obs"   for the sub-observer longitude;
                            "sun"   for the sub-solar longitude;
                            "oha"   for the anti-observer longitude;
                            "sha"   for the anti-solar longitude, returning the
                                    solar hour angle.
                            Put "old-" in front of the last four for deprecated
                            definitions, which are slower but infinitesimally
                            more accurate.
        """

        event_key = Backplane.standardize_event_key(event_key)
        assert reference in {"j2000", "obs", "oha", "sun", "sha",
                             "old-obs", "old-oha", "old-sun", "old-sha"}
                            # The last four are deprecated but not deleted

        # Look up under the desired reference
        key = ("ring_longitude", event_key, reference)
        if key in self.backplanes.keys():
            return self.backplanes[key]

        # If it is not found with reference J2000, fill in those backplanes
        key_j2000 = key[:-1] + ("j2000",)
        if key_j2000 not in self.backplanes.keys():
            self._fill_ring_intercepts(event_key)

        # Now apply the reference longitude
        if reference == "j2000":
            return self.backplanes[key]

        if reference == "sun":
            ref_lon = self.sub_solar_longitude(event_key)
        elif reference == "sha":
            ref_lon = self.sub_solar_longitude(event_key) - np.pi
        elif reference == "obs":
            ref_lon = self.sub_observer_longitude(event_key)
        elif reference == "oha":
            ref_lon = self.sub_observer_longitude(event_key) - np.pi

        # These four options are deprecated but not deleted. The above versions
        # are much simpler and faster and the difference is infinitesimal.
        elif reference == "old-sun":
            ref_lon = self._sub_solar_ring_longitude(event_key)
        elif reference == "old-sha":
            ref_lon = self._sub_solar_ring_longitude(event_key) - np.pi
        elif reference == "old-obs":
            ref_lon = self._sub_observer_ring_longitude(event_key)
        elif reference == "old-oha":
            ref_lon = self._sub_observer_ring_longitude(event_key) - np.pi

        lon = (self.backplanes[key_j2000] - ref_lon) % Backplane.TWOPI
        self.register_backplane(key, lon)

        return self.backplanes[key]

    def ring_azimuth(self, event_key, reference="obs"):
        """The angle measured in the prograde direction from a reference
        direction to the local radial direction, as measured at the ring
        intercept point and projected into the ring plane. This value is 90 at
        the left ansa and 270 at the right ansa."

        The reference direction can be "obs" for the apparent departing
        direction of the photon, or "sun" for the (negative) apparent direction
        of the arriving photon.

        Input:
            event_key       key defining the ring surface event.
            reference       "obs" or "sun"; see discussion above.
        """

        event_key = Backplane.standardize_event_key(event_key)
        assert reference in ("obs", "sun")

        # Look up under the desired reference
        key = ("ring_azimuth", event_key, reference)
        if key in self.backplanes.keys():
            return self.backplanes[key]

        # If not found, fill in the ring events if necessary
        if ("ring_radius", event_key) not in self.backplanes.keys():
            self._fill_ring_intercepts(event_key)

        # reference = "obs"
        if reference == "obs":
            event = self.get_surface_event(event_key)
            ref = event.aberrated_dep()

        # reference = "sun"
        else:
            event = self.get_surface_event_with_arr(event_key)
            ref = -event.aberrated_arr()

        ref_angle = ref.as_scalar(1).arctan2(ref.as_scalar(0))
        rad_angle = event.pos.as_scalar(1).arctan2(event.pos.as_scalar(0))
        az = (rad_angle - ref_angle) % Backplane.TWOPI
        self.register_backplane(key, az)

        return self.backplanes[key]

    def ring_elevation(self, event_key, reference="obs"):
        """The angle between the the ring plane and the direction of a photon
        arriving or departing from the ring intercept point. The angle is
        positive on the side of the ring plane where rotation is prograde;
        negative on the opposite side.

        The reference direction can be "obs" for the apparent departing
        direction of the photon, or "sun" for the (negative) apparent direction
        of the arriving photon.

        Input:
            event_key       key defining the ring surface event.
            reference       "obs" or "sun"; see discussion above.
        """

        event_key = Backplane.standardize_event_key(event_key)
        assert reference in ("obs", "sun")

        # Look up under the desired reference
        key = ("ring_elevation", event_key, reference)
        if key in self.backplanes.keys():
            return self.backplanes[key]

        # If not found, fill in the ring events if necessary
        if ("ring_radius", event_key) not in self.backplanes.keys():
            self._fill_ring_intercepts(event_key)

        # reference = "obs"
        if reference == "obs":
            event = self.get_surface_event(event_key)
            dir = event.aberrated_dep()

        # reference = "sun"
        else:
            event = self.get_surface_event_with_arr(event_key)
            dir = -event.aberrated_arr()

        el = Backplane.HALFPI - event.perp.sep(dir)
        self.register_backplane(key, el)

        return self.backplanes[key]

    def _fill_ring_intercepts(self, event_key):
        """Internal method to fill in the ring intercept geometry backplanes.
        """

        # Get the ring intercept coordinates
        event_key = Backplane.standardize_event_key(event_key)
        event = self.get_surface_event(event_key)
        assert event.surface.COORDINATE_TYPE == "polar"

        (r,lon) = event.surface.event_as_coords(event, axes=2)

        self.register_backplane(("ring_radius", event_key), r)
        self.register_backplane(("ring_longitude", event_key, "j2000"), lon)

    # Deprecated...
    def _sub_observer_ring_longitude(self, event_key):
        """Sub-observer longitude at the ring center, but evaluated at the ring
        intercept time. Used only internally. DEPRECATED.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("_sub_observer_ring_longitude", event_key)
        if key in self.backplanes.keys():
            return self.backplanes[key]

        # At each intercept time, determine the outgoing direction to the
        # observer from the center of the planet
        event = self.get_surface_event(event_key)
        center_event = Event(event.time, Vector3.ZERO, Vector3.ZERO,
                                         event.origin_id, event.frame_id)
        obs_path = path_.Waypoint(self.obs_event.origin_id)
        ignore = obs_path.photon_from_event(center_event)

        surface = Backplane.get_surface(event_key[0])
        assert surface.COORDINATE_TYPE == "polar"
        (r,lon) = surface.coords_from_vector3(center_event.aberrated_dep(),
                                              axes=2)

        self.register_backplane(key, lon.unmasked())
        return self.backplanes[key]

    # Deprecated...
    def _sub_solar_ring_longitude(self, event_key):
        """Sub-solar longitude at the ring center, but evaluated at the ring
        intercept time. Used only internally. DEPRECATED.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("_sub_solar_ring_longitude", event_key)
        if key in self.backplanes.keys():
            return self.backplanes[key]

        # At each intercept time, determine the incoming direction from the Sun
        # to the center of the planet
        event = self.get_surface_event(event_key)
        center_event = Event(event.time, Vector3.ZERO, Vector3.ZERO,
                                         event.origin_id, event.frame_id)
        ignore = path_.Waypoint("SUN").photon_to_event(center_event)

        surface = Backplane.get_surface(event_key[0])
        assert event.surface.COORDINATE_TYPE == "polar"
        (r,lon) = surface.coords_from_vector3(-center_event.aberrated_arr(),
                                              axes=2)

        self.register_backplane(key, lon.unmasked())
        return self.backplanes[key]

    def ring_incidence_angle(self, event_key):
        """Incidence_angle angle of the arriving photons at the local ring
        surface. According to the standard convention for rings, this must be
        <= pi/2. DEPRECATED; use incidence_angle() instead.
        """

        return self.incidence_angle(event_key)

    def ring_emission_angle(self, event_key):
        """Emission angle of the departing photons at the local ring surface.
        According to the standard convention for rings, this must be < pi/2 on
        the sunlit side of the rings and > pi/2 on the dark side. DEPRECATED;
        use emission_angle() instead.
        """

        return self.emission_angle(event_key)

    ############################################################################
    # Ring plane geometry, surface intercept only
    #   ring_radial_resolution()
    #   ring_angular_resolution()
    ############################################################################

    def ring_radial_resolution(self, event_key):
        """Projected radial resolution in km/pixel at the ring intercept point.

        Input:
            event_key       key defining the ring surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("ring_radial_resolution", event_key)
        try:
            return self.backplanes[key]
        except KeyError: pass

        event = self.get_surface_event_w_derivs(event_key)
        assert event.surface.COORDINATE_TYPE == "polar"

        (rad,lon) = event.surface.event_as_coords(event, axes=2,
                                                         derivs=(True,False))

        drad_duv = rad.d_dpos * event.pos.d_dlos * self.meshgrid.dlos_duv
        res = drad_duv.as_pair().norm()

        self.register_backplane(key, res)
        return self.backplanes[key]

    def ring_angular_resolution(self, event_key):
        """Projected angular resolution in radians/pixel at the ring intercept
        point.

        Input:
            event_key       key defining the ring surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("ring_angular_resolution", event_key)
        try:
            return self.backplanes[key]
        except KeyError: pass

        event = self.get_surface_event_w_derivs(event_key)
        assert event.surface.COORDINATE_TYPE == "polar"

        (rad,lon) = event.surface.event_as_coords(event, axes=2,
                                                         derivs=(False,True))

        dlon_duv = lon.d_dpos * event.pos.d_dlos * self.meshgrid.dlos_duv
        res = dlon_duv.as_pair().norm()

        self.register_backplane(key, res)
        return self.backplanes[key]

    ############################################################################
    # Ring ansa geometry, surface intercept only
    #   ansa_radius()
    #   ansa_altitude()
    #   ansa_longitude()
    ############################################################################

    def ansa_radius(self, event_key, radius_type="right"):
        """Radius of the ring ansa intercept point in the image.

        Input:
            event_key       key defining the ring surface event.
        """

        # Look up under the desired radius type
        event_key = Backplane.standardize_event_key(event_key)
        key0 = ("ansa_radius", event_key)
        key = key0 + (radius_type,)
        if key in self.backplanes.keys():
            return self.backplanes[key]

        # If not found, look up the default "right"
        assert radius_type in ("right", "left", "positive")

        key_default = key0 + ("right",)
        if key_default not in self.backplanes.keys():
            self._fill_ansa_intercepts(event_key)

            backplane = self.backplanes[key_default]
            if radius_type == "left":
                backplane = -backplane
            else:
                backplane = abs(backplane)

            self.register_backplane(key, backplane)

        return self.backplanes[key]

    def ansa_altitude(self, event_key):
        """Elevation of the ring ansa intercept point in the image.

        Input:
            event_key       key defining the ring surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("ansa_altitude", event_key)
        if key not in self.backplanes.keys():
            self._fill_ansa_intercepts(event_key)

        return self.backplanes[key]

    def ansa_longitude(self, event_key, reference="j2000"):
        """Longitude of the ansa intercept point in the image.

        Input:
            event_key       key defining the ring surface event.
            reference       defines the location of zero longitude.
                            "j2000" for the J2000 ascending node;
                            "obs"   for the sub-observer longitude;
                            "sun"   for the sub-solar longitude;
                            "oha"   for the anti-observer longitude;
                            "sha"   for the anti-solar longitude, returning the
                                    solar hour angle.
                            Put "old-" in front of the last four for deprecated
                            definitions, which are slower but infinitesimally
                            more accurate.
        """

        event_key = Backplane.standardize_event_key(event_key)
        assert reference in {"j2000", "obs", "oha", "sun", "sha",
                             "old-obs", "old-oha", "old-sun", "old-sha"}
                            # The last four are deprecated but not deleted

        # Look up under the desired reference
        key0 = ("ansa_longitude", event_key)
        key = key0 + (reference,)
        if key in self.backplanes.keys():
            return self.backplanes[key]

        # If it is not found with reference J2000, fill in those backplanes
        key_j2000 = key0 + ("j2000",)
        if key_j2000 not in self.backplanes.keys():
            self._fill_ansa_longitudes(event_key)

        # Now apply the reference longitude
        if reference == "j2000":
            return self.backplanes[key]

        if reference == "sun":
            ref_lon = self.sub_solar_longitude(event_key)
        elif reference == "sha":
            ref_lon = self.sub_solar_longitude(event_key) - np.pi
        elif reference == "obs":
            ref_lon = self.sub_observer_longitude(event_key)
        elif reference == "oha":
            ref_lon = self.sub_observer_longitude(event_key) - np.pi

        # These four options are deprecated but not deleted. The above versions
        # are much simpler and faster and the difference is infinitesimal.
        elif reference == "old-sun":
            ref_lon = self._sub_solar_ansa_longitude(event_key)
        elif reference == "old-sha":
            ref_lon = self._sub_solar_ansa_longitude(event_key) - np.pi
        elif reference == "old-obs":
            ref_lon = self._sub_observer_ansa_longitude(event_key)
        elif reference == "old-oha":
            ref_lon = self._sub_observer_ansa_longitude(event_key) - np.pi

        lon = (self.backplanes[key_j2000] - ref_lon) % Backplane.TWOPI
        self.register_backplane(key, lon)

        return self.backplanes[key]

    def _fill_ansa_intercepts(self, event_key):
        """Internal method to fill in the ansa intercept geometry backplanes.
        """

        # Get the ansa intercept coordinates
        event_key = Backplane.standardize_event_key(event_key)
        event = self.get_surface_event(event_key)
        assert event.surface.COORDINATE_TYPE == "cylindrical"

        (r,z) = event.surface.event_as_coords(event, axes=2)

        self.register_backplane(("ansa_radius", event_key, "right"), r)
        self.register_backplane(("ansa_altitude", event_key), z)

    def _fill_ansa_longitudes(self, event_key):
        """Internal method to fill in the ansa intercept longitude backplane
        in J2000 coordinates.
        """

        # Get the ansa intercept event
        event_key = Backplane.standardize_event_key(event_key)
        event = self.get_surface_event(event_key)
        assert event.surface.COORDINATE_TYPE == "cylindrical"

        # Get the longitude in the associated ring plane
        (r,lon) = event.surface.ringplane.event_as_coords(event, axes=2)

        self.register_backplane(("ansa_longitude", event_key, "j2000"), lon)

    # Deprecated
    def _sub_observer_ansa_longitude(self, event_key):
        """Sub-observer longitude at the planet center, but evaluated at the
        ansa intercept time. Used only internally. DEPRECATED.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("_sub_observer_ansa_longitude", event_key)
        if key in self.backplanes.keys():
            return self.backplanes[key]

        # At each intercept time, determine the outgoing direction to the
        # observer from the center of the planet
        event = self.get_surface_event(event_key)
        center_event = Event(event.time, Vector3.ZERO, Vector3.ZERO,
                                         event.origin_id, event.frame_id)
        obs_path = path_.Waypoint(self.obs_event.origin_id)
        ignore = obs_path.photon_from_event(center_event)

        surface = Backplane.get_surface(event_key[0]).ringplane
        (r,lon) = surface.coords_from_vector3(center_event.aberrated_dep(),
                                              axes=2)

        self.register_backplane(key, lon.unmasked())
        return self.backplanes[key]

    # Deprecated
    def _sub_solar_ansa_longitude(self, event_key):
        """Sub-solar longitude at the planet center, but evaluated at the ansa
        intercept time. Used only internally. DEPRECATED.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("_sub_solar_ansa_longitude", event_key)
        if key in self.backplanes.keys():
            return self.backplanes[key]

        # At each intercept time, determine the incoming direction from the Sun
        # to the center of the planet
        event = self.get_surface_event(event_key)
        center_event = Event(event.time, Vector3.ZERO, Vector3.ZERO,
                                         event.origin_id, event.frame_id)
        ignore = path_.Waypoint("SUN").photon_to_event(center_event)

        surface = Backplane.get_surface(event_key[0]).ringplane
        (r,lon) = surface.coords_from_vector3(-center_event.aberrated_arr(),
                                              axes=2)

        self.register_backplane(key, lon.unmasked())
        return self.backplanes[key]

    ############################################################################
    # Ansa resolution, surface intercepts only
    #
    # Radius keys: ("ansa_radial_resolution", event_key)
    # Elevation keys: ("ansa_vertical_resolution", event_key)
    ############################################################################

    def ansa_radial_resolution(self, event_key):
        """Projected radial resolution in km/pixel at the ring ansa intercept
        point.

        Input:
            event_key       key defining the ring surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("ansa_radial_resolution", event_key)
        try:
            return self.backplanes[key]
        except KeyError: pass

        event = self.get_surface_event_w_derivs(event_key)
        assert event.surface.COORDINATE_TYPE == "cylindrical"

        (r,z) = event.surface.event_as_coords(event, axes=2,
                                                     derivs=(True,False))

        dr_duv = r.d_dpos * event.pos.d_dlos * self.meshgrid.dlos_duv
        res = dr_duv.as_pair().norm()

        self.register_backplane(key, res)
        return self.backplanes[key]

    def ansa_vertical_resolution(self, event_key):
        """Projected radial resolution in km/pixel at the ring ansa intercept
        point.

        Input:
            event_key       key defining the ring surface event.
        """

        event_key = Backplane.standardize_event_key(event_key)
        key = ("ansa_vertical_resolution", event_key)
        try:
            return self.backplanes[key]
        except KeyError: pass

        event = self.get_surface_event_w_derivs(event_key)
        assert event.surface.COORDINATE_TYPE == "cylindrical"

        (r,z) = event.surface.event_as_coords(event, axes=2,
                                                     derivs=(False,True))

        dz_duv = z.d_dpos * event.pos.d_dlos * self.meshgrid.dlos_duv
        res = dz_duv.as_pair().norm()

        self.register_backplane(key, res)
        return self.backplanes[key]

    ############################################################################
    # Masks
    ############################################################################

    def where_intercepted(self, event_key):
        """Returns a mask containing True wherever the surface was intercepted.
        """

        event_key  = Backplane.standardize_event_key(event_key)
        key = ("where_intercepted", event_key)
        if key not in self.backplanes.keys():
            event = self.get_surface_event(event_key)
            mask = self.mask_as_scalar(np.logical_not(event.mask))
            self.register_backplane(key, mask)

        return self.backplanes[key]

    def where_inside_shadow(self, event_key, shadow_body):
        """Returns a mask containing True wherever the surface is in the shadow
        of a second body."""

        event_key = Backplane.standardize_event_key(event_key)
        shadow_body = Backplane.standardize_event_key(shadow_body)
        key = ("where_inside_shadow", event_key, shadow_body[0])
        if key not in self.backplanes.keys():
            event = self.get_surface_event_with_arr(event_key)
            shadow_event = self.get_surface_event(shadow_body + event_key)
            mask = self.mask_as_scalar(np.logical_not(event.mask) &
                                       np.logical_not(shadow_event.mask))
            self.register_backplane(key, mask)

        return self.backplanes[key]

    def where_outside_shadow(self, event_key, shadow_body):
        """Returns a mask containing True wherever the surface is outside the
        shadow of a second body."""

        event_key  = Backplane.standardize_event_key(event_key)
        shadow_body = Backplane.standardize_event_key(shadow_body)
        key = ("where_outside_shadow", event_key, shadow_body[0])
        if key not in self.backplanes.keys():
            event = self.get_surface_event_with_arr(event_key)
            shadow_event = self.get_surface_event(shadow_body + event_key)
            mask = self.mask_as_scalar(np.logical_not(event.mask) &
                                       shadow_event.mask)
            self.register_backplane(key, mask)

        return self.backplanes[key]

    def where_in_front(self, event_key, back_body):
        """Returns a mask containing True wherever the first surface is in front
        of the second surface. This is also True where the back_body is not
        behind the front body at all."""

        event_key = Backplane.standardize_event_key(event_key)
        back_body  = Backplane.standardize_event_key(back_body)
        key = ("where_in_front", event_key, back_body[0])
        if key not in self.backplanes.keys():

            # A surface is in front if it is unmasked and the second surface is
            # either masked or further away.
            front_unmasked = np.logical_not(
                                    self.get_surface_event(event_key).mask)
            back_masked = self.get_surface_event(back_body).mask
            mask = self.mask_as_scalar(front_unmasked & (back_masked |
                                            (self.distance(event_key).vals <
                                             self.distance(back_body).vals)))
            self.register_backplane(key, mask)

        return self.backplanes[key]

    def where_in_back(self, event_key, front_body):
        """Returns a mask containing True wherever first surface is behind the
        second surface."""

        event_key = Backplane.standardize_event_key(event_key)
        front_body = Backplane.standardize_event_key(front_body)

        key = ("where_in_back", event_key, front_body[0])
        if key not in self.backplanes.keys():

            # A surface is in back if it is unmasked and the second surface is
            # both unmasked and closer.
            back_unmasked  = np.logical_not(
                                    self.get_surface_event(event_key).mask)
            front_unmasked = np.logical_not(
                                    self.get_surface_event(front_body).mask)
            mask = self.mask_as_scalar(back_unmasked & front_unmasked &
                                    (self.distance(event_key).vals >
                                     self.distance(front_body).vals))
            self.register_backplane(key, mask)

        return self.backplanes[key]

    def where_sunward(self, event_key):
        """Returns a mask containing True wherever the surface of a body is
        facing toward the Sun."""

        event_key = Backplane.standardize_event_key(event_key)
        key = ("where_sunward",) + event_key
        if key not in self.backplanes.keys():
            incidence = self.incidence_angle(event_key)
            mask = self.mask_as_scalar((incidence.vals <= Backplane.HALFPI) &
                                       np.logical_not(incidence.mask))
            self.register_backplane(key, mask)

        return self.backplanes[key]

    def where_antisunward(self, event_key):
        """Returns a mask containing True wherever the surface of a body is
        facing away fron the Sun."""

        event_key = Backplane.standardize_event_key(event_key)
        key = ("where_antisunward",) + event_key
        if key not in self.backplanes.keys():
            incidence = self.incidence_angle(event_key)
            mask = self.mask_as_scalar((incidence.vals > Backplane.HALFPI) &
                                       np.logical_not(incidence.mask))
            self.register_backplane(key, mask)

        return self.backplanes[key]

    ############################################################################
    # Masks derived from backplanes
    ############################################################################

    def where_below(self, backplane_key, value):
        """Returns a mask that contains True wherever the value of the given
        backplane is less than or equal to the specified value."""

        backplane_key = Backplane.standardize_backplane_key(backplane_key)
        key = ("where_below", backplane_key, value)
        if key not in self.backplanes.keys():
            backplane = self.evaluate(backplane_key)
            mask = self.mask_as_scalar((backplane.vals <= value) &
                                       np.logical_not(backplane.mask))
            self.register_backplane(key, mask)

        return self.backplanes[key]

    def where_above(self, backplane_key, value):
        """Returns a mask that contains True wherever the value of the given
        backplane is greater than or equal to the specified value."""

        backplane_key = Backplane.standardize_backplane_key(backplane_key)
        key = ("where_above", backplane_key, value)
        if key not in self.backplanes.keys():
            backplane = self.evaluate(backplane_key)
            mask = self.mask_as_scalar((backplane.vals >= value) &
                                       np.logical_not(backplane.mask))
            self.register_backplane(key, mask)

        return self.backplanes[key]

    def where_between(self, backplane_key, low, high):
        """Returns a mask that contains True wherever the value of the given
        backplane is between the specified values, inclusive."""

        backplane_key = Backplane.standardize_backplane_key(backplane_key)
        key = ("where_between", backplane_key, low, high)
        if key not in self.backplanes.keys():
            backplane = self.evaluate(backplane_key)
            mask = self.mask_as_scalar((backplane.vals >= low) &
                                       (backplane.vals <= high) &
                                       np.logical_not(backplane.mask))
            self.register_backplane(key, mask)

        return self.backplanes[key]

    def where_not(self, backplane_key):
        """Returns a mask that contains True wherever the value of the given
        backplane is False."""

        backplane_key = Backplane.standardize_backplane_key(backplane_key)
        key = ("where_not", backplane_key)
        if key not in self.backplanes.keys():
            backplane = self.evaluate(backplane_key)
            self.register_backplane(key, ~backplane)

        return self.backplanes[key]

    def where_any(self, *backplane_keys):
        """Returns a mask that contains True wherever any of the given
        backplanes is True."""

        key = ("where_any",) + backplane_keys
        if key not in self.backplanes.keys():
            backplane = self.evaluate(backplane_keys[0])
            for next_mask in backplane_keys[1:]:
                backplane |= self.evaluate(next_mask)

            self.register_backplane(key, backplane)

        return self.backplanes[key]

    def where_all(self, *backplane_keys):
        """Returns a mask that contains True wherever all of the given
        backplanes are True."""

        key = ("where_all",) + backplane_keys
        if key not in self.backplanes.keys():
            backplane = self.evaluate(backplane_keys[0])
            for next_mask in backplane_keys[1:]:
                backplane &= self.evaluate(next_mask)

            self.register_backplane(key, backplane)

        return self.backplanes[key]

    ############################################################################
    # Borders
    ############################################################################

    def _border_above_or_below(self, sign, backplane_key, value):
        """Defines the locus of points surrounding the region where the
        backplane either above (greater than or equal to) or below (less than or
        equal to) a specified value."""

        backplane_key = Backplane.standardize_backplane_key(backplane_key)

        if sign > 0:
            key = ("border_above", backplane_key, value)
        else:
            key = ("border_below", backplane_key, value)

        if key not in self.backplanes.keys():
            backplane = sign * (self.evaluate(backplane_key) - value)
            border = np.zeros(self.meshgrid.shape, dtype="bool")

            axes = len(backplane.shape)
            for axis in range(axes):
                xbackplane = backplane.swapaxes(0, axis)
                xborder = border.swapaxes(0, axis)

                xborder[:-1] |= ((xbackplane[:-1].vals >= 0) &
                                 (xbackplane[1:].vals  < 0))
                xborder[1:]  |= ((xbackplane[1:].vals  >= 0) &
                                 (xbackplane[:-1].vals < 0))

            self.register_backplane(key, Scalar(border &
                                                np.logical_not(backplane.mask)))

        return self.backplanes[key]

    def border_above(self, backplane_key, value):
        """Defines the locus of points surrounding the region where the
        backplane is greater than or equal to a specified value."""

        return self._border_above_or_below(+1, backplane_key, value)

    def border_below(self, backplane_key, value):
        """Defines the locus of points surrounding the region where the
        backplane is less than or equal to a specified value."""

        return self._border_above_or_below(-1, backplane_key, value)

    def border_atop(self, backplane_key, value):
        """Defines the locus of points straddling the boder between the region
        where the backplane is below and where it is above the specified value.
        It selects the pixels that fall closest to the transition."""

        backplane_key = Backplane.standardize_backplane_key(backplane_key)
        key = ("border_atop", backplane_key, value)
        if key not in self.backplanes.keys():
            absval = self.evaluate(backplane_key) - value
            sign = absval.sign()
            absval *= sign

            border = (absval == 0.)

            axes = len(absval.shape)
            for axis in range(axes):
                xabs = absval.vals.swapaxes(0, axis)
                xsign = sign.vals.swapaxes(0, axis)
                xborder = border.vals.swapaxes(0, axis)

                xborder[:-1] |= ((xsign[:-1] == -xsign[1:]) &
                                 (xabs[:-1] <= xabs[1:]))
                xborder[1:]  |= ((xsign[1:] == -xsign[:-1]) &
                                 (xabs[1:] <= xabs[:-1]))

            self.register_backplane(key, border)

        return self.backplanes[key]

    def _border_outside_or_inside(self, backplane_key, value):
        """Defines the locus of points that fall on the outer edge of a mask.
        "Outside" (value = False) identifies the first False pixels outside each
        area of True pixels; "Inside" (value = True) identifies the last True
        pixels adjacent to an area of False pixels."""

        backplane_key = Backplane.standardize_backplane_key(backplane_key)

        if value:
            key = ("border_inside", backplane_key)
        else:
            key = ("border_outside", backplane_key)

        if key not in self.backplanes.keys():
            backplane = self.evaluate(backplane_key) ^ np.logical_not(value)
            # Reverses the backplane if value is False
            border = np.zeros(backplane.shape, dtype="bool")

            axes = len(backplane.shape)
            for axis in range(axes):
                xbackplane = backplane.swapaxes(0, axis)
                xborder = border.swapaxes(0, axis)

                xborder[:-1] |= ((xbackplane[:-1].vals ^ xbackplane[1:].vals) &
                                  xbackplane[:-1].vals)
                xborder[1:]  |= ((xbackplane[1:].vals ^ xbackplane[:-1].vals) &
                                  xbackplane[1:].vals)

            self.register_backplane(key, Scalar(border))

        return self.backplanes[key]

    def border_inside(self, backplane_key):
        """Defines the locus of True pixels adjacent to a region of False
        pixels."""

        return self._border_outside_or_inside(backplane_key, True)

    def border_outside(self, backplane_key):
        """Defines the locus of False pixels adjacent to a region of True
        pixels."""

        return self._border_outside_or_inside(backplane_key, False)

    ############################################################################
    # Method to access a backplane or mask by key
    ############################################################################

    # Here we use the class introspection capabilities of Python to provide a
    # general way to generate any backplane based on its key. This makes it
    # possible to access any backplane via its key rather than by making an
    # explicit call to the function that generates the key.

    # Here we keep track of all the function names that generate backplanes. For
    # security, we disallow evaluate() to access any function not in this list.

    CALLABLES = {
        "right_ascension", "declination",
        "center_right_ascension", "center_declination",

        "distance", "light_time", "event_time", "resolution",
        "center_distance", "center_light_time", "center_time",
            "center_resolution",

        "incidence_angle", "emission_angle", "phase_angle",
            "scattering_angle", "lambert_law",
        "center_incidence_angle", "center_emission_angle", "center_phase_angle",
            "center_scattering_angle",

        "longitude", "latitude",
        "sub_longitude", "sub_latitude",
        "finest_resolution", "coarsest_resolution",
        "altitude",

        "ring_radius", "ring_longitude", "ring_azimuth", "ring_elevation",
        "ring_radial_resolution", "ring_angular_resolution",
        "ansa_radius", "ansa_altitude", "ansa_longitude",
        "ansa_radial_resolution", "ansa_vertical_resolution",

        "where_intercepted",
        "where_inside_shadow", "where_outside_shadow",
        "where_in_front", "where_in_back",
        "where_sunward", "where_antisunward",
        "where_below", "where_above", "where_between",
        "where_not", "where_any", "where_all",

        "border_below", "border_above", "border_atop",
        "border_inside", "border_outside"}

    def evaluate(self, backplane_key):
        """Evaluates the backplane or mask based on the given key. Equivalent
        to calling the function directly, but the name of the function is the
        first argument in the tuple passed to the function."""

        if type(backplane_key) == type(""): backplane_key = (backplane_key,)

        func = backplane_key[0]
        if func not in Backplane.CALLABLES:
            raise ValueError("unrecognized backplane function: " + func)

        return Backplane.__dict__[func].__call__(self, *backplane_key[1:])

################################################################################
# UNIT TESTS
################################################################################

import unittest

UNITTEST_PRINT = False
UNITTEST_LOGGING = False
UNITTEST_FILESPEC = "test_data/cassini/ISS/W1573721822_1.IMG"
UNITTEST_UNDERSAMPLE = 16

def show_info(title, array):
    """Internal method to print summary information and display images as
    desired."""

    global UNITTEST_PRINT
    if not UNITTEST_PRINT: return

    print title

    # Mask summary
    if array.vals.dtype == np.dtype("bool"):
        count = np.sum(array.vals)
        total = np.size(array.vals)
        percent = int(count / float(total) * 100. + 0.5)
        print "  ", (count, total-count),
        print (percent, 100-percent), "(True, False pixels)"

    # Unmasked backplane summary
    elif array.mask is False:
        minval = np.min(array.vals)
        maxval = np.max(array.vals)
        if minval == maxval:
            print "  ", minval
        else:
            print "  ", (minval, maxval), "(min, max)"

    # Masked backplane summary
    else:
        print "  ", (np.min(array.vals),
                       np.max(array.vals)), "(unmasked min, max)"
        print "  ", (array.min(),
                       array.max()), "(masked min, max)"
        total = np.size(array.mask)
        masked = np.sum(array.mask)
        percent = int(masked / float(total) * 100. + 0.5)
        print "  ", (masked, total-masked),
        print         (percent, 100-percent),"(masked, unmasked pixels)"

####################################################
# TestCase begins here
####################################################

class Test_Backplane(unittest.TestCase):

    def runTest(self):

        import oops_.registry as registry
        registry.initialize_frame_registry()
        registry.initialize_path_registry()
        registry.initialize_body_registry()

        import oops.inst.cassini.iss as iss

        if UNITTEST_LOGGING: config.LOGGING.on("        ")

        snap = iss.from_file(UNITTEST_FILESPEC)
        meshgrid = Meshgrid.for_fov(snap.fov, undersample=UNITTEST_UNDERSAMPLE,
                                    swap=True)

        bp = Backplane(snap, meshgrid)

        test = bp.right_ascension()
        show_info("Right ascension (deg)", test * constants.DPR)

        test = bp.right_ascension(apparent=True)
        show_info("Right ascension (deg, apparent)", test * constants.DPR)

        test = bp.declination()
        show_info("Declination (deg)", test * constants.DPR)

        test = bp.declination(apparent=True)
        show_info("Declination (deg, apparent)", test * constants.DPR)

        test = bp.distance("saturn")
        show_info("Range to Saturn (km)", test)

        test = bp.distance(("sun","saturn"))
        show_info("Saturn distance to Sun (km)", test)

        test = bp.light_time("saturn")
        show_info("Light-time from Saturn (sec)", test)

        test = bp.incidence_angle("saturn")
        show_info("Saturn incidence angle (deg)", test * constants.DPR)

        test = bp.emission_angle("saturn")
        show_info("Saturn emission angle (deg)", test * constants.DPR)

        test = bp.phase_angle("saturn")
        show_info("Saturn phase angle (deg)", test * constants.DPR)

        test = bp.scattering_angle("saturn")
        show_info("Saturn scattering angle (deg)", test * constants.DPR)

        test = bp.longitude("saturn")
        show_info("Saturn longitude (deg)", test * constants.DPR)

        test = bp.longitude("saturn", direction="west")
        show_info("Saturn longitude westward (deg)", test * constants.DPR)

        test = bp.longitude("saturn", minimum=-180)
        show_info("Saturn longitude with -180 minimum (deg)",
                                                    test * constants.DPR)

        test = bp.longitude("saturn", reference="iau")
        show_info("Saturn longitude wrt IAU frame (deg)",
                                                    test * constants.DPR)

        test = bp.longitude("saturn", reference="sun")
        show_info("Saturn longitude wrt Sun (deg)", test * constants.DPR)

        test = bp.longitude("saturn", reference="sha")
        show_info("Saturn longitude wrt SHA (deg)", test * constants.DPR)

        test = bp.longitude("saturn", reference="obs")
        show_info("Saturn longitude wrt observer (deg)",
                                                    test * constants.DPR)

        test = bp.longitude("saturn", reference="oha")
        show_info("Saturn longitude wrt OHA (deg)", test * constants.DPR)

        test = bp.latitude("saturn", lat_type="centric")
        show_info("Saturn geocentric latitude (deg)", test * constants.DPR)

        test = bp.latitude("saturn", lat_type="graphic")
        show_info("Saturn geographic latitude (deg)", test * constants.DPR)

        test = bp.finest_resolution("saturn")
        show_info("Saturn finest surface resolution (km)", test)

        test = bp.coarsest_resolution("saturn")
        show_info("Saturn coarsest surface resolution (km)", test)

        test = bp.ring_radius("saturn_main_rings")
        show_info("Ring radius (km)", test)

        test = bp.ring_radius("saturn_main_rings").unmasked()
        show_info("Ring radius unmasked (km)", test)

        test = bp.ring_longitude("saturn_main_rings",reference="j2000")
        show_info("Ring longitude wrt J2000 (deg)", test * constants.DPR)

        test = bp.ring_longitude("saturn_main_rings", reference="sun")
        show_info("Ring longitude wrt Sun (deg)", test * constants.DPR)

        test = bp.ring_longitude("saturn_main_rings", reference="sha")
        show_info("Ring longitude wrt SHA (deg)", test * constants.DPR)

        test = bp.ring_longitude("saturn_main_rings", reference="obs")
        show_info("Ring longitude wrt observer (deg)",
                                                    test * constants.DPR)

        test = bp.ring_longitude("saturn_main_rings", reference="oha")
        show_info("Ring longitude wrt OHA (deg)", test * constants.DPR)

        test = bp.distance("saturn_main_rings")
        show_info("Range to rings (km)", test)

        test = bp.light_time("saturn_main_rings")
        show_info("Light time from rings (sec)", test)

        test = bp.distance(("sun", "saturn_main_rings"))
        show_info("Ring distance to Sun (km)", test)

        test = bp.incidence_angle("saturn_main_rings")
        show_info("Ring incidence angle (deg)", test * constants.DPR)

        test = bp.emission_angle("saturn_main_rings")
        show_info("Ring emission angle (deg)", test * constants.DPR)

        test = bp.phase_angle("saturn_main_rings")
        show_info("Ring phase angle (deg)", test * constants.DPR)

        test = bp.ring_radial_resolution("saturn_main_rings")
        show_info("Ring radial resolution (km/pixel)", test)

        test = bp.ring_angular_resolution("saturn_main_rings")
        show_info("Ring angular resolution (deg/pixel)", test * constants.DPR)

        test = bp.where_intercepted("saturn")
        show_info("Saturn intercepted mask", test)

        test = bp.where_in_front("saturn", "saturn_main_rings")
        show_info("Saturn in front of rings", test)

        test = bp.where_in_back("saturn", "saturn_main_rings")
        show_info("Saturn in front of rings", test)

        test = bp.where_inside_shadow("saturn", "saturn_main_rings")
        show_info("Saturn in front of rings", test)

        test = bp.where_outside_shadow("saturn", "saturn_main_rings")
        show_info("Saturn in front of rings", test)

        test = bp.where_sunward("saturn")
        show_info("Saturn sunward", test)

        test = bp.where_antisunward("saturn")
        show_info("Saturn anti-sunward", test)

        test = bp.where_intercepted("saturn_main_rings")
        show_info("Rings intercepted mask", test)

        test = bp.where_in_front("saturn_main_rings", "saturn")
        show_info("Rings in front of Saturn", test)

        test = bp.where_in_back("saturn_main_rings", "saturn")
        show_info("Rings in front of Saturn", test)

        test = bp.where_inside_shadow("saturn_main_rings", "saturn")
        show_info("Rings in front of Saturn", test)

        test = bp.where_outside_shadow("saturn_main_rings", "saturn")
        show_info("Rings in front of Saturn", test)

        test = bp.where_sunward("saturn_main_rings")
        show_info("Rings sunward", test)

        test = bp.where_antisunward("saturn_main_rings")
        show_info("Rings anti-sunward", test)

        test = bp.right_ascension()
        show_info("Right ascension the old way (deg)", test * constants.DPR)

        test = bp.evaluate("right_ascension")
        show_info("Right ascension via evaluate() (deg)", test * constants.DPR)

        test = bp.where_intercepted("saturn")
        show_info("Saturn intercepted the old way", test)

        test = bp.evaluate(("where_intercepted", "saturn"))
        show_info("Saturn where intercepted via evaluate()", test)

        test = bp.where_sunward("saturn")
        show_info("Saturn sunward the old way", test)

        test = bp.evaluate(("where_sunward", "saturn"))
        show_info("Saturn sunward via evaluate()", test)

        test = bp.where_below(("incidence_angle", "saturn"), Backplane.HALFPI)
        show_info("Saturn sunward via where_below()", test)

        test = bp.evaluate(("where_antisunward", "saturn"))
        show_info("Saturn antisunward via evaluate()", test)

        test = bp.where_above(("incidence_angle", "saturn"), Backplane.HALFPI)
        show_info("Saturn antisunward via where_above()", test)

        test = bp.where_between(("incidence_angle", "saturn"), Backplane.HALFPI,
                                                               3.2)
        show_info("Saturn antisunward via where_between()", test)

        test = bp.where_intercepted("saturn")
        show_info("Saturn intercepted the old way", test)

        mask = bp.where_intercepted("saturn")
        test = bp.border_inside(mask)
        show_info("Saturn inside border", test)

        test = bp.border_outside(mask)
        show_info("Saturn outside border", test)

        test = bp.where_below(("ring_radius", "saturn_main_rings"), 100000.)
        show_info("Ring area below 100,000 km", test)

        test = bp.border_below(("ring_radius", "saturn_main_rings"), 100000.)
        show_info("Ring border below 100,000 km", test)

        test = bp.border_atop(("ring_radius", "saturn_main_rings"), 100000.)
        show_info("Ring border atop 100,000 km", test)

        test = bp.border_atop(("ring_radius", "saturn_main_rings"), 100000.)
        show_info("Ring border above 100,000 km", test)

        test = bp.evaluate(("border_atop", ("ring_radius",
                                            "saturn_main_rings"), 100000.))
        show_info("Ring border above 100,000 km via evaluate()", test)

        ########################
        # Testing ansa events and new notation

        test = bp.ring_radius("saturn_main_rings")
        show_info("Saturn main ring radius the old way (km)", test)

        test = bp.distance("saturn:ring")
        show_info("Saturn:ring radius (km)", test)

        test = bp.distance("saturn:ansa")
        show_info("Saturn:ansa distance (km)", test)

        test = bp.ansa_radius("saturn:ansa")
        show_info("Saturn:ansa radius (km)", test)

        test = bp.ansa_altitude("saturn:ansa")
        show_info("Saturn:ansa altitude (km)", test)

        test = bp.ansa_radial_resolution("saturn:ansa")
        show_info("Saturn:ansa radial resolution (km)", test)

        test = bp.ansa_vertical_resolution("saturn:ansa")
        show_info("Saturn:ansa vertical resolution (km)", test)

        test = bp.ansa_vertical_resolution("saturn_main_rings:ansa")
        show_info("Saturn_main_ring:ansa vertical resolution (km)", test)

        test = bp.finest_resolution("saturn_main_rings:ansa")
        show_info("Saturn_main_ring:ansa finest resolution (km)", test)

        test = bp.finest_resolution("saturn_main_rings:ansa")
        show_info("Saturn_main_ring:ansa coarsest resolution (km)", test)

        ########################
        # Testing ansa longitudes

        test = bp.ansa_longitude("saturn:ansa")
        show_info("Saturn ansa longitude wrt J2000 (deg)", test * constants.DPR)

        test = bp.ansa_longitude("saturn:ansa", "obs")
        show_info("Saturn ansa longitude wrt observer (deg)",
                                                           test * constants.DPR)

        test = bp.ansa_longitude("saturn:ansa", "sun")
        show_info("Saturn ansa longitude wrt Sun (deg)", test * constants.DPR)

        ########################
        # Testing ring azimuth & elevation

        test = bp.ring_azimuth("saturn:ring")
        show_info("Saturn ring azimuth wrt observer(deg)", test * constants.DPR)

        compare = bp.ring_longitude("saturn:ring", "obs")
        diff = test - compare
        show_info("Saturn ring azimuth wrt observer minus longitude (deg)",
                                                           diff * constants.DPR)

        test = bp.ring_azimuth("saturn:ring", reference="sun")
        show_info("Saturn ring azimuth wrt Sun (deg)", test * constants.DPR)

        compare = bp.ring_longitude("saturn:ring", "sun")
        diff = test - compare
        show_info("Saturn ring azimuth wrt Sun minus longitude (deg)",
                                                           diff * constants.DPR)

        test = bp.ring_elevation("saturn:ring", reference="obs")
        show_info("Saturn ring elevation wrt observer (deg)",
                                                           test * constants.DPR)
        compare = bp.emission_angle("saturn:ring")
        diff = test + compare
        show_info("Saturn ring emission wrt observer plus emission (deg)",
                                                           diff * constants.DPR)

        test = bp.ring_elevation("saturn:ring", reference="sun")
        show_info("Saturn ring elevation wrt Sun (deg)", test * constants.DPR)

        compare = bp.incidence_angle("saturn:ring")
        diff = test + compare
        show_info("Saturn ring elevation wrt Sun plus incidence (deg)",
                                                           diff * constants.DPR)

        ########################
        # Ring scalars, other tests 5/14/12

        if UNITTEST_PRINT:
            print
            print "Sub-solar Saturn planetocentric latitude (deg) =",
            print bp.sub_solar_latitude("saturn").vals * constants.DPR

            print "Sub-solar Saturn planetographic latitude (deg) =",
            print bp.sub_solar_latitude("saturn",
                                        "graphic").vals * constants.DPR

            print "Sub-solar Saturn longitude wrt IAU (deg) =",
            print bp.sub_solar_longitude("saturn").vals * constants.DPR

            print "Solar distance to Saturn center (km) =",
            print bp.center_distance("saturn", "sun").vals

            print
            print "Sub-observer Saturn planetocentric latitude (deg) =",
            print bp.sub_observer_latitude("saturn").vals * constants.DPR

            print "Sub-observer Saturn planetographic latitude (deg) =",
            print bp.sub_observer_latitude("saturn",
                                           "graphic").vals * constants.DPR

            print "Sub-observer Saturn longitude wrt IAU (deg) =",
            print bp.sub_observer_longitude("saturn").vals * constants.DPR

            print "Observer distance to Saturn center (km) =",
            print bp.observer_distance_to_center("saturn").vals

            print
            print "Sub-solar ring latitude (deg) =",
            print bp.sub_solar_latitude("saturn:ring").vals * constants.DPR

            print "Sub-solar ring longitude wrt J2000 (deg) =",
            print bp.sub_solar_longitude("saturn:ring").vals * constants.DPR

            print "Solar distance to ring center (km) =",
            print bp.center_distance("saturn:ring", "sun").vals

            print "Sub-observer ring latitude (deg) =",
            print bp.sub_observer_latitude("saturn:ring").vals * constants.DPR

            print "Sub-observer ring longitude wrt J2000 (deg) =",
            print bp.sub_observer_longitude("saturn:ring").vals * constants.DPR

            print "Observer distance to ring center (km) =",
            print bp.observer_distance_to_center("saturn:ring").vals
            print

        test = bp.ring_longitude("saturn_main_rings", reference="sun")
        show_info("Ring longitude wrt Sun (deg)", test * constants.DPR)

        test = bp.ring_longitude("saturn_main_rings", reference="old-sun")
        show_info("Ring longitude wrt Sun (deg), old way", test * constants.DPR)

        test = bp.ring_longitude("saturn_main_rings", reference="sha")
        show_info("Ring longitude wrt SHA (deg)", test * constants.DPR)

        test = bp.ring_longitude("saturn_main_rings", reference="old-sha")
        show_info("Ring longitude wrt SHA (deg), old way", test * constants.DPR)

        test = bp.ring_longitude("saturn_main_rings", reference="obs")
        show_info("Ring longitude wrt observer (deg)", test * constants.DPR)

        test = bp.ring_longitude("saturn_main_rings", reference="old-obs")
        show_info("Ring longitude wrt observer (deg), old way",
                                                    test * constants.DPR)

        test = bp.ring_longitude("saturn_main_rings", reference="oha")
        show_info("Ring longitude wrt OHA (deg)", test * constants.DPR)

        test = bp.ring_longitude("saturn_main_rings", reference="old-oha")
        show_info("Ring longitude wrt OHA (deg), old way", test * constants.DPR)

        test = bp.ansa_longitude("saturn_main_rings:ansa", reference="sun")
        show_info("Ansa longitude wrt Sun (deg)", test * constants.DPR)

        test = bp.ansa_longitude("saturn_main_rings:ansa", reference="old-sun")
        show_info("Ansa longitude wrt Sun (deg), old way", test * constants.DPR)

        test = bp.ansa_longitude("saturn_main_rings:ansa", reference="sha")
        show_info("Ansa longitude wrt SHA (deg)", test * constants.DPR)

        test = bp.ansa_longitude("saturn_main_rings:ansa", reference="old-sha")
        show_info("Ansa longitude wrt SHA (deg), old way", test * constants.DPR)

        test = bp.ansa_longitude("saturn_main_rings:ansa", reference="obs")
        show_info("Ansa longitude wrt observer (deg)", test * constants.DPR)

        test = bp.ansa_longitude("saturn_main_rings:ansa", reference="old-obs")
        show_info("Ansa longitude wrt observer (deg), old way",
                                                    test * constants.DPR)

        test = bp.ansa_longitude("saturn_main_rings:ansa", reference="oha")
        show_info("Ansa longitude wrt OHA (deg)", test * constants.DPR)

        test = bp.ansa_longitude("saturn_main_rings:ansa", reference="old-oha")
        show_info("Ansa longitude wrt OHA (deg), old way", test * constants.DPR)

        ########################
        # Limb and resolution, 6/6/12

        test = bp.altitude("saturn:limb")
        show_info("Limb altitude (km)", test)

        test = bp.longitude("saturn:limb")
        show_info("Limb longitude (deg)", test * constants.DPR)

        test = bp.latitude("saturn:limb")
        show_info("Limb latitude (deg)", test * constants.DPR)

        test = bp.longitude("saturn:limb", reference="obs", minimum=-180)
        show_info("Limb longitude wrt observer, -180 (deg)",
                                                        test * constants.DPR)

        test = bp.latitude("saturn:limb", lat_type="graphic")
        show_info("Limb planetographic latitude (deg)", test * constants.DPR)

        test = bp.latitude("saturn:limb", lat_type="centric")
        show_info("Limb planetocentric latitude (deg)", test * constants.DPR)

        test = bp.resolution("saturn:limb", "u")
        show_info("Limb resolution horizontal (km/pixel)", test)

        test = bp.resolution("saturn:limb", "v")
        show_info("Limb resolution vertical (km/pixel)", test)

        ########################
        # Testing empty events
        # DO NOT PUT ANY MORE UNIT TESTS BELOW THIS LINE; BACKPLANE IS REPLACED

        snap = iss.from_file(UNITTEST_FILESPEC)
        meshgrid = Meshgrid.for_fov(snap.fov, undersample=UNITTEST_UNDERSAMPLE,
                                    swap=True)
        bp = Backplane(snap, meshgrid)

        # Override some internals...
        old_obs = bp.obs_event
        bp.obs_event = Event(Scalar(old_obs.time, mask=True),
                             old_obs.pos, old_obs.vel,
                             old_obs.origin_id, old_obs.frame_id,
                             arr = old_obs.arr)

        bp.surface_events_w_derivs = {(): bp.obs_event}
        bp.surface_events = {(): bp.obs_event.plain()}

        test = bp.distance("saturn")
        show_info("Range to Saturn, entirely masked (km)", test)

        test = bp.phase_angle("saturn")
        show_info("Phase angle at Saturn, entirely masked (deg)",
                                                test * constants.DPR)

        config.LOGGING.off()

        registry.initialize_frame_registry()
        registry.initialize_path_registry()
        registry.initialize_body_registry()
        iss.ISS.reset()

########################################
if __name__ == '__main__':
    unittest.main(verbosity=2)
################################################################################
