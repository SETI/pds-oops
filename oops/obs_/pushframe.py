################################################################################
# oops/obs_/pushframe.py: Subclass Pushframe of class Observation
################################################################################

#from IPython import embed   ## TODO: remove

from IPython import embed   ## TODO: remove

import numpy as np
from polymath import *

from oops.obs_.observation   import Observation
from oops.cadence_.cadence   import Cadence
from oops.cadence_.sequence  import Sequence
from oops.path_.path         import Path
from oops.path_.multipath    import MultiPath
from oops.frame_.frame       import Frame
from oops.body               import Body
from oops.event              import Event

#*******************************************************************************
# Pushframe
#*******************************************************************************
class Pushframe(Observation):
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    """
    A Pushframe is an Observation consisting of a 2-D image made up of lines
    of pixels, each exposed and shifted progressively to track a scene moving
    through the FOV at a constant rate.
    """
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

    INVENTORY_IMPLEMENTED = True

    PACKRAT_ARGS = ['axes', 'tstart', 'cadence', 'fov', 'path', 'frame',
                    '**subfields']

    #===========================================================================
    # __init__
    #===========================================================================
    def __init__(self, axes, cadence, fov, path, frame, **subfields):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Constructor for a Pushframe.

        Input:
            axes        a list or tuple of strings, with one value for each axis
                        in the associated data array. A value of 'u' or 'ut'
                        should appear at the location of the array's u-axis;
                        'vt' or 'v' should appear at the location of the array's
                        v-axis. The 't' suffix is used for the one of these axes
                        that is swept by the time-delayed integration.

            cadence     a Cadence object defining the start time and duration of
                        each consecutive line of the pushframe.  Alternatively,
                        a dictionary containing the following entries, from 
                        which a cadence object is constructed:

                         tstart: Observation start time.
                         nexp:   Number of exposures in the observation.
                         texp:    Exposure time for each observation.

            fov         a FOV (field-of-view) object, which describes the field
                        of view including any spatial distortion. It maps
                        between spatial coordinates (u,v) and instrument
                        coordinates (x,y).

            path        the path waypoint co-located with the instrument.

            frame       the wayframe of a coordinate frame fixed to the optics
                        of the instrument. This frame should have its Z-axis
                        pointing outward near the center of the line of sight,
                        with the X-axis pointing rightward and the y-axis
                        pointing downward.

            subfields   a dictionary containing all of the optional attributes.
                        Additional subfields may be included as needed.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

        #--------------------------------------------------
        # Basic properties
        #--------------------------------------------------
        self.fov = fov
        self.path = Path.as_waypoint(path)
        self.frame = Frame.as_wayframe(frame)

        #--------------------------------------------------
        # Axes
        #--------------------------------------------------
        self.axes = list(axes)
        assert (('u' in self.axes and 'vt' in self.axes) or
                ('v' in self.axes and 'ut' in self.axes))

        if 'ut' in self.axes:
            self.u_axis = self.axes.index('ut')
            self.v_axis = self.axes.index('v')
            self.t_axis = self.u_axis
            self.cross_scan_uv_index = 0
            self.along_scan_uv_index = 1
        else:
            self.u_axis = self.axes.index('u')
            self.v_axis = self.axes.index('vt')
            self.t_axis = self.v_axis
            self.cross_scan_uv_index = 1
            self.along_scan_uv_index = 0

        self.swap_uv = (self.u_axis > self.v_axis)

        duv_dt_basis_vals = np.zeros(2)
        duv_dt_basis_vals[self.cross_scan_uv_index] = 1.
        self.duv_dt_basis = Pair(duv_dt_basis_vals)

        #--------------------------------------------------
        # Shape / Size
        #--------------------------------------------------
        self.uv_shape = tuple(self.fov.uv_shape.values)
        self.along_scan_shape = self.uv_shape[self.along_scan_uv_index]
        self.cross_scan_shape = self.uv_shape[self.cross_scan_uv_index]

        self.uv_size = Pair.ONES

        self.shape = len(axes) * [1]
        self.shape[self.u_axis] = self.uv_shape[0]
        self.shape[self.v_axis] = self.uv_shape[1]

        #--------------------------------------------------
        # Cadence
        #--------------------------------------------------
        if isinstance(cadence, Cadence): self.cadence = cadence
        else: self.cadence = self._default_cadence(cadence)

        assert len(self.cadence.shape) == 1
        assert (self.fov.uv_shape.vals[self.cross_scan_uv_index] ==
                self.cadence.shape[0])

        #--------------------------------------------------
        # Basic timing
        #--------------------------------------------------
        self.time = self.cadence.time
        self.midtime = self.cadence.midtime

        #---------------------------------------------------------------
        # Fractional timing
        #  For each pixel, determine the fractional window within each 
        #  exposure that corresponds to the scene geometry
        #---------------------------------------------------------------
        time0 = self.cadence.time_at_tstep(0)
        time1 = time0 + self.cadence.texp[self.cadence.steps-1]

        times = self.cadence.time_range_at_tstep(
	                                np.indices([self.shape[self.t_axis]]))
        dtimes = times[1] - times[0]

        tfrac0 = ((time0 - times[0])/dtimes).vals.T
        tfrac1 = ((time1 - times[0])/dtimes).vals.T
        self.tfrac = ( Scalar.as_scalar(np.broadcast_to(tfrac0, self.shape)), 
                       Scalar.as_scalar(np.broadcast_to(tfrac1, self.shape)) )

        #--------------------------------------------------
        # Optional subfields
        #--------------------------------------------------
        self.subfields = {}
        for key in subfields.keys():
            self.insert_subfield(key, subfields[key])
    #===========================================================================

    def _test():
        print('test')

    #===========================================================================
    # _default_cadence
    #===========================================================================
    def _default_cadence(self, dict):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Return a cadence object a dictionary of parameters.

        Input:
            dict        Dictionary containing the following entries:

                         tstart: Observation start time.
                         nexp:   Number of exposures in the observation.
                         exp:    Exposure time for each observation.

        Return:         Cadence object.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        tstart = dict['tstart']
        nexp = dict['nexp']
        texp = dict['texp']
        nlines = self.shape[self.t_axis]

        nstages = np.clip(np.arange(nlines-1,-1,-1)+1, 0, nexp) 
        exp = nstages * texp
        tstart = (nexp - nstages) * texp + tstart
		
        return Sequence(tstart, exp)
    #===========================================================================



    #===========================================================================
    # uvt
    #===========================================================================
    def uvt(self, indices, fovmask=False):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Return coordinates (u,v) and time t for indices into the data array.

        This method supports non-integer index values.

        Input:
            indices     a Tuple of array indices.
            fovmask     True to mask values outside the field of view.

        Return:         (uv, time)
            uv          a Pair defining the values of (u,v) associated with the
                        array indices.
            time        a Scalar defining the time in seconds TDB associated
                        with the array indices.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        indices = Vector.as_vector(indices)
        uv = indices.to_pair((self.u_axis,self.v_axis))
        
        #---------------------------
        # Create the time Scalar
        #---------------------------
        tstep = indices.to_scalar(self.t_axis)
        time = self.cadence.time_at_tstep(tstep, mask=fovmask)

        #------------------------------
        # Apply mask if necessary
        #------------------------------
        if fovmask:
            is_outside = self.uv_is_outside(uv, inclusive=True)
            if np.any(is_outside):
                uv = uv.mask_where(is_outside)
                time = time.mask_where(is_outside)

        return (uv, time)
    #===========================================================================



    #===========================================================================
    # uvt_range 
    #===========================================================================
    def uvt_range(self, indices, fovmask=False):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Return ranges of coordinates and time for integer array indices.

        Input:
            indices     a Tuple of integer array indices.
            fovmask     True to mask values outside the field of view.

        Return:         (uv_min, uv_max, time_min, time_max)
            uv_min      a Pair defining the minimum values of (u,v) associated
                        the pixel.
            uv_max      a Pair defining the maximum values of (u,v).
            time_min    a Scalar defining the minimum time associated with the
                        pixel. It is given in seconds TDB.
            time_max    a Scalar defining the maximum time value.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        indices = Vector.as_vector(indices).as_int()

        uv_min = indices.to_pair((self.u_axis,self.v_axis))
        uv_max = uv_min + self.uv_size

        tstep = indices.to_scalar(self.t_axis)
        (time_min,
         time_max) = self.cadence.time_range_at_tstep(tstep, mask=fovmask)

        if fovmask:
            is_outside = self.uv_is_outside(uv_min, inclusive=False)
            if np.any(is_outside):
                mask = indices.mask | time_min.mask | is_outside
                uv_min = uv_min.mask_where(mask)
                uv_max = uv_max.mask_where(mask)
                time_min = time_min.mask_where(mask)
                time_max = time_max.mask_where(mask)

        return (uv_min, uv_max, time_min, time_max)
    #===========================================================================



    #===========================================================================
    # uv_range_at_tstep
    #===========================================================================
    def uv_range_at_tstep(self, *tstep):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Return a tuple defining the range of (u,v) coordinates active at a
        particular time step.

        Input:
            tstep       a time step index (one or two integers).

        Return:         a tuple (uv_min, uv_max)
            uv_min      a Pair defining the minimum values of (u,v) coordinates
                        active at this time step.
            uv_min      a Pair defining the maximum values of (u,v) coordinates
                        active at this time step (exclusive).
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        return (Pair(0,0), Pair.as_pair(self.shape) - (1,1))
    #===========================================================================



    #===========================================================================
    # times_at_uv
    #===========================================================================
    def times_at_uv(self, uv_pair, fovmask=False):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Return start and stop times of the specified spatial pixel (u,v).

        Input:
            uv_pair     a Pair of spatial (u,v) coordinates in and observation's
                        field of view. The coordinates need not be integers, but
                        any fractional part is truncated.
            fovmask     True to mask values outside the field of view.

        Return:         a tuple containing Scalars of the start time and stop
                        time of each (u,v) pair, as seconds TDB.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        uv_pair = uv_pair.as_int()
        tstep = uv_pair.to_scalar(self.cross_scan_uv_index)
        (time0, time1) = self.cadence.time_range_at_tstep(tstep, mask=fovmask)

        if fovmask:
            is_outside = self.uv_is_outside(uv_pair, inclusive=True)
            if np.any(is_outside):
                time0 = time0.mask_where(is_outside)
                time1 = time1.mask_where(is_outside)

        return (time0, time1)
    #===========================================================================
    


    #===========================================================================
    # sweep_duv_dt
    #===========================================================================
    def sweep_duv_dt(self, uv_pair):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Return the mean local sweep speed of the instrument along (u,v) axes.

        Input:
            uv_pair     a Pair of spatial indices (u,v).

        Return:         a Pair containing the local sweep speed in units of
                        pixels per second in the (u,v) directions.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        uv_pair = Pair.as_pair(uv_pair)
        tstep = uv_pair.to_scalar(self.cross_slit_uv_index)

        return self.duv_dt_basis / self.cadence.tstride_at_tstep(tstep)
    #===========================================================================



    #===========================================================================
    # time_shift
    #===========================================================================
    def time_shift(self, dtime):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Return a copy of the observation object with a time-shift.

        Input:
            dtime       the time offset to apply to the observation, in units of
                        seconds. A positive value shifts the observation later.

        Return:         a (shallow) copy of the object with a new time.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        obs = Pushframe(self.axes, self.cadence.time_shift(dtime),
                        self.fov, self.path, self.frame)

        for key in self.subfields.keys():
            obs.insert_subfield(key, self.subfields[key])

        return obs
    #===========================================================================



    #===========================================================================
    # inventory
    #===========================================================================
    def inventory(self, bodies, expand=0., return_type='list', fov=None,
                        quick={}, converge={}, time_frac=0.5):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Return the body names that appear unobscured inside the FOV.

        Restrictions: All inventory calculations are performed at a single
        observation time specified by time_frac. All bodies are assumed to be
        spherical.

        Input:
            bodies      a list of the names of the body objects to be included
                        in the inventory.
            expand      an optional angle in radians by which to extend the
                        limits of the field of view. This can be used to
                        accommodate pointing uncertainties. XXX NOT IMPLEMENTED XXX
            return_type 'list' returns the inventory as a list of names.
                        'flags' returns the inventory as an array of boolean
                                flag values in the same order as bodies.
                        'full' returns the inventory as a dictionary of
                                dictionaries. The main dictionary is indexed by
                                body name. The subdictionaries contain
                                attributes of the body in the FOV.
            fov         use this fov; if None, use self.fov.
            quick       an optional dictionary to override the configured
                        default parameters for QuickPaths and QuickFrames; False
                        to disable the use of QuickPaths and QuickFrames. The
                        default configuration is defined in config.py.
            converge    an optional dictionary of parameters to override the
                        configured default convergence parameters. The default
                        configuration is defined in config.py.
            time_frac   fractional time from the beginning to the end of the
                        observation for which the inventory applies. 0. for the
                        beginning; 0.5 for the midtime, 1. for the end time.

        Return:         list, array, or dictionary

            If return_type is 'list', it returns a list of the names of all the
            body objects that fall at least partially inside the FOV and are
            not completely obscured by another object in the list.

            If return_type is 'flags', it returns a boolean array containing
            True everywhere that the body falls at least partially inside the
            FOV and is not completely obscured.

            If return_type is 'full', it returns a dictionary with one entry
            per body that falls at least partially inside the FOV and is not
            completely obscured. Each dictionary entry is itself a dictionary
            containing data about the body in the FOV:

                body_data['name']          The body name
                body_data['center_uv']     The U,V coord of the center point
                body_data['center']        The Vector3 direction of the center
                                           point
                body_data['range']         The range in km
                body_data['outer_radius']  The outer radius of the body in km
                body_data['inner_radius']  The inner radius of the body in km
                body_data['resolution']    The resolution (km/pix) in the (U,V)
                                           directions at the given range.
                body_data['u_min']         The minimum U value covered by the
                                           body (clipped to the FOV size)
                body_data['u_max']         The maximum U value covered by the
                                           body (clipped to the FOV size)
                body_data['v_min']         The minimum V value covered by the
                                           body (clipped to the FOV size)
                body_data['v_max']         The maximum V value covered by the
                                           body (clipped to the FOV size)
                body_data['u_min_unclipped']  Same as above, but not clipped
                body_data['u_max_unclipped']  to the FOV size.
                body_data['v_min_unclipped']
                body_data['v_max_unclipped']
                body_data['u_pixel_size']  The number of pixels (non-integer)
                body_data['v_pixel_size']  covered by the diameter of the body
                                           in each direction.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        assert return_type in ('list', 'flags', 'full')

        if fov is None:
            fov = self.fov

        body_names = [Body.as_body_name(body) for body in bodies]
        bodies  = [Body.as_body(body) for body in bodies]
        nbodies = len(bodies)

        path_ids = [body.path for body in bodies]
        multipath = MultiPath(path_ids)

        obs_time = self.time[0] + time_frac * (self.time[1] - self.time[0])
        obs_event = Event(obs_time, Vector3.ZERO, self.path, self.frame)
        (_,
         arrival_event) = multipath.photon_to_event(obs_event, quick=quick,
                                                    converge=converge)

        centers = arrival_event.neg_arr_ap
        ranges = centers.norm()
        radii = Scalar([body.radius for body in bodies])
        radius_angles = (radii/ranges).arcsin()

        inner_radii = Scalar([body.inner_radius for body in bodies])
        inner_angles = (inner_radii / ranges).arcsin()

        #-----------------------------------------------------------------------
        # This array equals True for each body falling somewhere inside the FOV
        #-----------------------------------------------------------------------
        falls_inside = np.empty(nbodies, dtype='bool')
        for i in range(nbodies):
            falls_inside[i] = fov.sphere_falls_inside(centers[i], radii[i])

        #--------------------------------------------------------------------
        # This array equals True for each body completely hidden by another
        #--------------------------------------------------------------------
        is_hidden = np.zeros(nbodies, dtype='bool')
        for i in range(nbodies):
          if not falls_inside[i]: continue

          for j in range(nbodies):
            if not falls_inside[j]: continue

            if ranges[i] < ranges[j]: continue
            if radius_angles[i] > inner_angles[j]: continue

            sep = centers[i].sep(centers[j])
            if sep < inner_angles[j] - radius_angles[i]:
                is_hidden[i] = True

        flags = falls_inside & ~is_hidden

        #------------------------
        # Return as flags
        #------------------------
        if return_type == 'flags':
            return flags

        #---------------------
        # Return as list
        #---------------------
        if return_type == 'list':
            ret_list = []
            for i in range(nbodies):
                if flags[i]: ret_list.append(body_names[i])
            return ret_list

        #-----------------------
        # Return full info
        #-----------------------
        returned_dict = {}

        u_scale = fov.uv_scale.vals[0]
        v_scale = fov.uv_scale.vals[1]
        body_uv = fov.uv_from_los(arrival_event.neg_arr_ap).vals
        for i in range(nbodies):
            body_data = {}
            body_data['name'] = body_names[i]
            body_data['inside'] = flags[i]
            body_data['center_uv'] = body_uv[i]
            body_data['center'] = centers[i].vals
            body_data['range'] = ranges[i].vals
            body_data['outer_radius'] = radii[i].vals
            body_data['inner_radius'] = inner_radii[i].vals

            u_res = ranges[i] * self.fov.uv_scale.to_scalar(0).tan()
            v_res = ranges[i] * self.fov.uv_scale.to_scalar(1).tan()
            body_data['resolution'] = Pair.from_scalars(u_res, v_res).vals

            u = body_uv[i][0]
            v = body_uv[i][1]
            u_min_unclipped = int(np.floor(u-radius_angles[i].vals/u_scale))
            u_max_unclipped = int(np.ceil( u+radius_angles[i].vals/u_scale))
            v_min_unclipped = int(np.floor(v-radius_angles[i].vals/v_scale))
            v_max_unclipped = int(np.ceil( v+radius_angles[i].vals/v_scale))

            body_data['u_min_unclipped'] = u_min_unclipped
            body_data['u_max_unclipped'] = u_max_unclipped
            body_data['v_min_unclipped'] = v_min_unclipped
            body_data['v_max_unclipped'] = v_max_unclipped

            body_data['u_min'] = np.clip(u_min_unclipped, 0, self.uv_shape[0]-1)
            body_data['u_max'] = np.clip(u_max_unclipped, 0, self.uv_shape[0]-1)
            body_data['v_min'] = np.clip(v_min_unclipped, 0, self.uv_shape[1]-1)
            body_data['v_max'] = np.clip(v_max_unclipped, 0, self.uv_shape[1]-1)

            body_data['u_pixel_size'] = radius_angles[i].vals/u_scale*2
            body_data['v_pixel_size'] = radius_angles[i].vals/v_scale*2

            returned_dict[body_names[i]] = body_data

        return returned_dict
    #===========================================================================


#*******************************************************************************



################################################################################
# UNIT TESTS
################################################################################

import unittest

#*******************************************************************************
# Test_Pushframe
#*******************************************************************************
class Test_Pushframe(unittest.TestCase):

    #===========================================================================
    # runTest
    #===========================================================================
    def runTest(self):
        return
        
        from oops.cadence_.metronome import Metronome
        from oops.fov_.flatfov import FlatFOV

        flatfov = FlatFOV((0.001,0.001), (10,20))
        cadence = Metronome(tstart=0., tstride=10., texp=10., steps=20)
        obs = Pushframe(axes=('u','vt'),
                        cadence=cadence, fov=flatfov, path='SSB', frame='J2000')

        indices = Vector([(0,0),(0,10),(0,20),(10,0),(10,10),(10,20),(10,21)])

        #-------------------------------
        # uvt() with fovmask == False
        #-------------------------------
        (uv,time) = obs.uvt(indices)
        
        
        
        
        
        

        self.assertFalse(np.any(uv.mask))
        self.assertFalse(np.any(time.mask))
        self.assertTrue(time.max() <= cadence.midtime)
        self.assertEqual(uv, Pair.as_pair(indices))

        #-------------------------------
        # uvt() with fovmask == True
        #-------------------------------
        (uv,time) = obs.uvt(indices, fovmask=True)
        
#        embed()
        return      #####################################

        self.assertTrue(np.all(uv.mask == np.array(6*[False] + [True])))
        self.assertTrue(np.all(time.mask == uv.mask))
        self.assertEqual(time[:6], cadence.tstride * indices.to_scalar(1)[:6])
        self.assertEqual(uv[:6], Pair.as_pair(indices)[:6])

        #--------------------------------------
        # uvt_range() with fovmask == False
        #--------------------------------------
        (uv_min, uv_max, time_min, time_max) = obs.uvt_range(indices)

        self.assertFalse(np.any(uv_min.mask))
        self.assertFalse(np.any(uv_max.mask))
        self.assertFalse(np.any(time_min.mask))
        self.assertFalse(np.any(time_max.mask))

        self.assertEqual(uv_min, Pair.as_pair(indices))
        self.assertEqual(uv_max, Pair.as_pair(indices) + (1,1))
        self.assertEqual(time_min, cadence.tstride * indices.to_scalar(1))
        self.assertEqual(time_max, time_min + cadence.texp)

        #----------------------------------------------------
        # uvt_range() with fovmask == False, new indices
        #----------------------------------------------------
        (uv_min, uv_max, time_min, time_max) = obs.uvt_range(indices+(0.2,0.9))

        self.assertFalse(np.any(uv_min.mask))
        self.assertFalse(np.any(uv_max.mask))
        self.assertFalse(np.any(time_min.mask))
        self.assertFalse(np.any(time_max.mask))

        self.assertEqual(uv_min, Pair.as_pair(indices))
        self.assertEqual(uv_max, Pair.as_pair(indices) + (1,1))
        self.assertEqual(time_min, cadence.tstride * indices.to_scalar(1))
        self.assertEqual(time_max, time_min + cadence.texp)

        #--------------------------------------------------
        # uvt_range() with fovmask == True, new indices
        #--------------------------------------------------
        (uv_min, uv_max, time_min, time_max) = obs.uvt_range(indices+(0.2,0.9),
                                                             fovmask=True)

        self.assertTrue(np.all(uv_min.mask == np.array(2*[False] + 5*[True])))
        self.assertTrue(np.all(uv_max.mask == uv_min.mask))
        self.assertTrue(np.all(time_min.mask == uv_min.mask))
        self.assertTrue(np.all(time_max.mask == uv_min.mask))

        self.assertEqual(uv_min[:2], Pair.as_pair(indices)[:2])
        self.assertEqual(uv_max[:2], Pair.as_pair(indices)[:2] + (1,1))
        self.assertEqual(time_min[:2], cadence.tstride *
                                       indices.to_scalar(1)[:2])
        self.assertEqual(time_max[:2], time_min[:2] + cadence.texp)

        #------------------------------------------
        # times_at_uv() with fovmask == False
        #------------------------------------------
        uv = Pair([(0,0),(0,20),(10,0),(10,20),(10,21)])

        (time0, time1) = obs.times_at_uv(uv)

        self.assertEqual(time0, cadence.tstride * uv.to_scalar(1))
        self.assertEqual(time1, time0 + cadence.texp)

        #-----------------------------------------
        # times_at_uv() with fovmask == True
        #-----------------------------------------
        (time0, time1) = obs.times_at_uv(uv, fovmask=True)

        self.assertTrue(np.all(time0.mask == 4*[False] + [True]))
        self.assertTrue(np.all(time1.mask == 4*[False] + [True]))
        self.assertEqual(time0[:4], cadence.tstride * uv.to_scalar(1)[:4])
        self.assertEqual(time1[:4], time0[:4] + cadence.texp)

        #----------------------------------------
        # Alternative axis order ('ut','v')
        #----------------------------------------
        cadence = Metronome(tstart=0., tstride=10., texp=10., steps=10)
        obs = Pushframe(axes=('ut','v'),
                        cadence=cadence, fov=flatfov, path='SSB', frame='J2000')

        indices = Vector([(0,0),(0,10),(0,20),(10,0),(10,10),(10,20),(10,21)])

        (uv,time) = obs.uvt(indices)

        self.assertEqual(uv, Pair.as_pair(indices))
        self.assertEqual(time, cadence.tstride * indices.to_scalar(0))

        (uv_min, uv_max, time_min, time_max) = obs.uvt_range(indices)

        self.assertEqual(uv_min, Pair.as_pair(indices))
        self.assertEqual(uv_max, Pair.as_pair(indices) + (1,1))
        self.assertEqual(time_min, cadence.tstride * indices.to_scalar(0))
        self.assertEqual(time_max, time_min + cadence.texp)

        (time0,time1) = obs.times_at_uv(indices)

        self.assertEqual(time0, cadence.tstride * uv.to_scalar(0))
        self.assertEqual(time1, time0 + cadence.texp)

        #-----------------------------------------------------------
        # Alternative uv_size and texp for discontinuous indices
        #-----------------------------------------------------------
        cadence = Metronome(tstart=0., tstride=10., texp=8., steps=10)
        obs = Pushframe(axes=('ut','v'),
                        cadence=cadence, fov=flatfov, path='SSB', frame='J2000')

        self.assertEqual(obs.time[1], 98.)

        self.assertEqual(obs.uvt((0,0))[1],  0.)
        self.assertEqual(obs.uvt((5,0))[1], 50.)
        self.assertEqual(obs.uvt((5,5))[1], 50.)

        eps = 1.e-14
        delta = 1.e-13
        self.assertTrue(abs(obs.uvt((6      ,0))[1] - 60.) < delta)
        self.assertTrue(abs(obs.uvt((6.25   ,0))[1] - 62.) < delta)
        self.assertTrue(abs(obs.uvt((6.5    ,0))[1] - 64.) < delta)
        self.assertTrue(abs(obs.uvt((6.75   ,0))[1] - 66.) < delta)
        self.assertTrue(abs(obs.uvt((7 - eps,0))[1] - 68.) < delta)
        self.assertTrue(abs(obs.uvt((7.     ,0))[1] - 70.) < delta)

        self.assertEqual(obs.uvt((0,0))[0], (0.,0.))
        self.assertEqual(obs.uvt((5,0))[0], (5.,0.))
        self.assertEqual(obs.uvt((5,5))[0], (5.,5.))

        self.assertTrue(abs(obs.uvt((6      ,0))[0] - (6.0,0.)) < delta)
        self.assertTrue(abs(obs.uvt((6.2    ,1))[0] - (6.1,1.)) < delta)
        self.assertTrue(abs(obs.uvt((6.4    ,2))[0] - (6.2,2.)) < delta)
        self.assertTrue(abs(obs.uvt((6.6    ,3))[0] - (6.3,3.)) < delta)
        self.assertTrue(abs(obs.uvt((6.8    ,4))[0] - (6.4,4.)) < delta)
        self.assertTrue(abs(obs.uvt((7 - eps,5))[0] - (6.5,5.)) < delta)
        self.assertTrue(abs(obs.uvt((7.     ,6))[0] - (7.0,6.)) < delta)

        self.assertTrue(abs(obs.uvt((1, 0      ))[0] - (1.,0.0)) < delta)
        self.assertTrue(abs(obs.uvt((2, 1.25   ))[0] - (2.,1.2)) < delta)
        self.assertTrue(abs(obs.uvt((3, 2.5    ))[0] - (3.,2.4)) < delta)
        self.assertTrue(abs(obs.uvt((4, 3.75   ))[0] - (4.,3.6)) < delta)
        self.assertTrue(abs(obs.uvt((5, 5 - eps))[0] - (5.,4.8)) < delta)
        self.assertTrue(abs(obs.uvt((5, 5.     ))[0] - (5.,5.0)) < delta)

        #--------------------------
        # Test the upper edge
        #--------------------------
        pair = (10-eps,20-eps)
        self.assertTrue(abs(obs.uvt(pair, True)[0].values[0] -  9.5) < delta)
        self.assertTrue(abs(obs.uvt(pair, True)[0].values[1] - 19.8) < delta)
        self.assertFalse(obs.uvt(pair, True)[0].mask)

        pair = (10,20-eps)
        self.assertTrue(abs(obs.uvt(pair, True)[0].values[0] -  9.5) < delta)
        self.assertTrue(abs(obs.uvt(pair, True)[0].values[1] - 19.8) < delta)
        self.assertFalse(obs.uvt(pair, True)[0].mask)

        pair = (10-eps,20)
        self.assertTrue(abs(obs.uvt(pair, True)[0].values[0] -  9.5) < delta)
        self.assertTrue(abs(obs.uvt(pair, True)[0].values[1] - 19.8) < delta)
        self.assertFalse(obs.uvt(pair, True)[0].mask)

        pair = (10,20)
        self.assertTrue(abs(obs.uvt(pair, True)[0].values[0] -  9.5) < delta)
        self.assertTrue(abs(obs.uvt(pair, True)[0].values[1] - 19.8) < delta)
        self.assertFalse(obs.uvt(pair, True)[0].mask)

        self.assertTrue(obs.uvt((10+eps,20), True)[0].mask)
        self.assertTrue(obs.uvt((10,20+eps), True)[0].mask)

        #----------------------
        # Try all at once
        #----------------------
        indices = Pair([(10-eps,20-eps), (10,20-eps), (10-eps,20), (10,20),
                        (10+eps,20), (10,20+eps)])

        (uv,t) = obs.uvt(indices, fovmask=True)
        self.assertTrue(np.all(t.mask == np.array(4*[False] + 2*[True])))

        #-------------------------------------------------
        # Alternative with uv_size and texp and axes
        #-------------------------------------------------
        obs = Pushframe(axes=('a','v','b','ut','c'),
                        cadence=cadence, fov=flatfov, path='SSB', frame='J2000')

        self.assertEqual(obs.time[1], 98.)

        self.assertEqual(obs.uvt((1,0,3,0,4))[1],  0.)
        self.assertEqual(obs.uvt((1,0,3,5,4))[1], 50.)
        self.assertEqual(obs.uvt((1,0,3,5,4))[1], 50.)

        eps = 1.e-14
        delta = 1.e-13
        self.assertTrue(abs(obs.uvt((1,0,0,6      ,0))[1] - 60.) < delta)
        self.assertTrue(abs(obs.uvt((1,0,0,6.25   ,0))[1] - 62.) < delta)
        self.assertTrue(abs(obs.uvt((1,0,0,6.5    ,0))[1] - 64.) < delta)
        self.assertTrue(abs(obs.uvt((1,0,0,6.75   ,0))[1] - 66.) < delta)
        self.assertTrue(abs(obs.uvt((1,0,0,7 - eps,0))[1] - 68.) < delta)
        self.assertTrue(abs(obs.uvt((1,0,0,7.     ,0))[1] - 70.) < delta)

        self.assertEqual(obs.uvt((0,0,0,0,0))[0], (0.,0.))
        self.assertEqual(obs.uvt((0,0,0,5,0))[0], (5.,0.))
        self.assertEqual(obs.uvt((0,5,0,5,0))[0], (5.,5.))

        self.assertTrue(abs(obs.uvt((1,0,4,6      ,7))[0] - (6.0,0.)) < delta)
        self.assertTrue(abs(obs.uvt((1,1,4,6.2    ,7))[0] - (6.1,1.)) < delta)
        self.assertTrue(abs(obs.uvt((1,2,4,6.4    ,7))[0] - (6.2,2.)) < delta)
        self.assertTrue(abs(obs.uvt((1,3,4,6.6    ,7))[0] - (6.3,3.)) < delta)
        self.assertTrue(abs(obs.uvt((1,4,4,6.8    ,7))[0] - (6.4,4.)) < delta)
        self.assertTrue(abs(obs.uvt((1,5,4,7 - eps,7))[0] - (6.5,5.)) < delta)
        self.assertTrue(abs(obs.uvt((1,6,4,7.     ,7))[0] - (7.0,6.)) < delta)

        self.assertTrue(abs(obs.uvt((1, 0      ,4,1,7))[0] - (1.,0.0)) < delta)
        self.assertTrue(abs(obs.uvt((1, 1.25   ,4,2,7))[0] - (2.,1.2)) < delta)
        self.assertTrue(abs(obs.uvt((1, 2.5    ,4,3,7))[0] - (3.,2.4)) < delta)
        self.assertTrue(abs(obs.uvt((1, 3.75   ,4,4,7))[0] - (4.,3.6)) < delta)
        self.assertTrue(abs(obs.uvt((1, 5 - eps,4,5,7))[0] - (5.,4.8)) < delta)
        self.assertTrue(abs(obs.uvt((1, 5.     ,4,5,7))[0] - (5.,5.0)) < delta)
    #===========================================================================


#*******************************************************************************


########################################
if __name__ == '__main__':
    unittest.main(verbosity=2)
################################################################################