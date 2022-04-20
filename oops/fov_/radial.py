################################################################################
# oops/fov_/radial.py: Radial subclass of FOV
################################################################################

from __future__ import print_function

from IPython import embed  ## TODO: remove

import numpy as np
import oops

from polymath import *
from oops.fov_.fov import FOV

#******************************************************************************
# Radial FOV class
#******************************************************************************
class Radial(FOV):
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    """The Radial subclass of FOV describes a field of view in which the
    distortion is described by a 1-D polynomial in distance from the image 
    center.
    """
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    DEBUG = False       # True to print(convergence steps on xy_from_uv())

    PACKRAT_ARGS = ['uv_scale', 'uv_shape', 'coefft_xy_from_uv', 'coefft_uv_from_xy',
                    'uv_los', 'uv_area', 'iters']


    #=========================================================================
    # __init__
    #=========================================================================
    def __init__(self, uv_scale, uv_shape, coefft_xy_from_uv=None,
                 coefft_uv_from_xy=None, uv_los=None, uv_area=None,
                 iters=8):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """Constructor for a RadialFOV.

        Inputs:
            uv_scale    a single value, tuple or Pair defining the ratios dx/du
                        and dy/dv. At the center of the FOV.  For example, if 
                        (u,v) are in units of  arcseconds, then
                            uv_scale = Pair((pi/180/3600.,pi/180/3600.))
                        Use the sign of the second element to define the
                        direction of increasing V: negative for up, positive for
                        down.

            uv_shape    a single value, tuple or Pair defining size of the field
                        of view in pixels. This number can be non-integral if
                        the detector is not composed of a rectangular array of
                        pixels.

            coefft_xy_from_uv
                        the coefficient array of the polynomial to convert 
                        U,V to X,Y. The array has shape [order+2], where 
                        coefft[i] is the coefficient on r**i, where 
                        r = sqrt((u-ulos)**2 + (v-vlos)**2), yielding x(u,v) 
			and y(u,v). All coefficients are 0 for i > order. If 
			None, then the polynomial for uv_from_xy is inverted.

            coefft_uv_from_xy
                        the coefficient array of the polynomial to convert 
                        X,Y to U,V. The array has shape [order+1], where 
                        coefft[i] is the coefficient on r**i, where 
                        r = sqrt((u-ulos)**2 + (v-vlos)**2), yielding x(u,v) 
			and y(u,v). All coefficients are 0 for i > order. If 
			None, then the polynomial for xy_from_uv is inverted.

            uv_los      a single value, tuple or Pair defining the (u,v)
                        coordinates of the nominal line of sight. By default,
                        this is the midpoint of the rectangle, i.e, uv_shape/2.

            uv_area     an optional parameter defining the nominal area of a
                        pixel in steradians after distortion has been removed.

            iters       the number of iterations of Newton's method to use when
                        inverting the distortion polynomial.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        self.coefft_xy_from_uv = None
        self.coefft_uv_from_xy = None
        
        if coefft_xy_from_uv is not None:
            self.coefft_xy_from_uv = np.asarray(coefft_xy_from_uv)
        if coefft_uv_from_xy is not None:
            self.coefft_uv_from_xy = np.asarray(coefft_uv_from_xy)

        assert (self.coefft_xy_from_uv is not None or
                self.coefft_uv_from_xy is not None)

        self.uv_scale = Pair.as_pair(uv_scale).as_readonly()
        self.uv_shape = Pair.as_pair(uv_shape).as_readonly()

        if uv_los is None:
            self.uv_los = self.uv_shape / 2.
        else:
            self.uv_los = Pair.as_pair(uv_los).as_float()
            self.uv_los.as_readonly()

        self.iters = iters
	
        self.flat_fov = \
                   oops.fov.FlatFOV(self.uv_scale, self.uv_shape, self.uv_los)


        if uv_area is None:
            self.uv_area = np.abs(self.uv_scale.vals[0] * self.uv_scale.vals[1])
        else:
            self.uv_area = uv_area
    #=========================================================================



    #=========================================================================
    # xy_from_uv
    #=========================================================================
    def xy_from_uv(self, uv, derivs=False):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """Return (x,y) camera frame coordinates given FOV coordinates (u,v).
        
        Input:
            uv       Pairs of arbitrary shape to be transformed from FOV
                     coordinates.
            derivs   If True, any derivatives in (u,v) get propagated into
                     the returned (x,y).
	    
        Output:      xy
            xy       Pairs of same shape as uv giving the transformed
                     FOV coordinates.

        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        
        #-----------------------------------------------------
        # Transform based on which types of coeffs are given
        #-----------------------------------------------------
        if self.coefft_xy_from_uv is not None:
            xy = self._apply_polynomial(uv, 
                             self.coefft_xy_from_uv, 
                                  self.flat_fov.xy_from_uv, derivs, from_='uv')
        else:
            xy = self._solve_polynomial(uv, 
                             self.coefft_uv_from_xy, 
                                  self.flat_fov.xy_from_uv, derivs, from_='uv')

        return xy
    #=========================================================================



    #=========================================================================
    # uv_from_xy
    #=========================================================================
    def uv_from_xy(self, xy, derivs=False):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """Return (u,v) FOV coordinates given (x,y) camera frame coordinates.
        
        Input:
            xy       Pairs of arbitrary shape to be transformed to FOV
                     coordinates.
            derivs   If True, any derivatives in (x,y) get propagated into
                     the returned (u,v).
	    
        Output:      uv
            uv       Pairs of same shape as xy giving the computed
                     FOV coordinates.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        xy = Pair.as_pair(xy, derivs)

        #-----------------------------------------------------
        # Transform based on which types of coeffs are given
        #-----------------------------------------------------
        if self.coefft_uv_from_xy is not None:
            uv = self._apply_polynomial(xy, 
                            self.coefft_uv_from_xy, 
                                  self.flat_fov.uv_from_xy, derivs, from_='xy')
        else:
            uv = self._solve_polynomial(xy, 
                            self.coefft_xy_from_uv, 
                                  self.flat_fov.uv_from_xy, derivs, from_='xy')
        
        return uv
    #=========================================================================



    #=========================================================================
    # _compute_polynomial
    #=========================================================================
    def _compute_polynomial(self, r, coefft, derivs):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """Compute the 1-D polynomial.
        
        Input:
            r        Scalar of arbitrary shape specifying the points at which 
                     to evaluate the polynomial.
            coefft   The coefficient array defining the polynomial.
            derivs   If True, derivatives are computed and included in the 
                     result.

        Output:      (f, deriv)
            f        Scalar of the same shape as r giving the values of 
                     the polynomial at each input point.
                """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        order = coefft.shape[0]-1
        
        #------------------------------------
	# Construct the powers of radius
        #------------------------------------
        r_powers = [1.]
        for k in range(1, order+1):
	    r_powers.append(r_powers[-1] * r)

        #-----------------------------------------------------------------
        # Evaluate the polynomial
        #
        # Start with the high-order terms and work downward, because this
        # improves accuracy. Stop at one because there are no zero-order 
        # terms.
        #-----------------------------------------------------------------
        f = 0.
        for i in range(order, -1, -1):
            f += coefft[i] * r_powers[i]

        #---------------------------------------------------
        # Calculate derivatives if necessary
        #---------------------------------------------------
        if derivs:
            df_dr = 0.
            for i in range(order, 0, -1):
                df_dr += i*coefft[i]*r_powers[i-1]
            f.insert_deriv('r', df_dr)
	
        return f
    #=========================================================================



    #=========================================================================
    # _apply_polynomial
    #=========================================================================
    def _apply_polynomial(self, pq, coefft, flat, derivs, from_=None):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """Apply the polynomial to pair (p,q) to return (a,b).
        
        Input:
            pq       Pairs of arbitrary shape specifying the points at which 
                     to evaluate the polynomial.
            coefft   The coefficient array defining the polynomial.
            derivs   If True, derivatives are computed and included in the 
                     result.
            from_    Source system, for labeling the derivatives, e.g., 'uv' 
                     or 'xy'.

        Output:      ab
            ab       Pairs of the same shape as pq giving the values of 
                     the polynomial at each input point.
                """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        assert from_ in ('uv', 'xy')
        dkey = from_
       
        #------------------------------------
	# Compute radii
        #------------------------------------
        pq.insert_deriv(dkey, Pair.IDENTITY)
        r = pq.norm()

        #-----------------------------------------------
	# Compute and apply the polynomial correction
        #-----------------------------------------------
        c = self._compute_polynomial(r, coefft, derivs=derivs)
        fab = flat(pq, derivs=derivs)
        ab = fab*c

        #------------------------------------------------
        # Propagate derivatives if necessary
        #------------------------------------------------
        ab.propagate_deriv(pq, dkey, dpq_dab, derivs)

        return ab
    #=========================================================================



    #=========================================================================
    # _solve_polynomial
    #=========================================================================
    def _solve_polynomial(self, ab, coefft, flat, derivs, from_=None):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """Solve the polynomial for an (a,b) pair to return (p,q).
        
        Input:
            ab       Pairs of arbitrary shape specifying the points at which
                     to invert the polynomial.
            coefft   The coefficient array defining the polynomial to invert.
            derivs   If True, derivatives are included in the output.
            from_    Source system, for labeling the derivatives, e.g., 'uv' 
                     or 'xy'.
	    
        Output:      pq
            pq       Pairs of of the same shape as ab giving the values of 
                     the inverted polynomial at each input point.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        assert from_ in ('uv', 'xy')
        dkey = from_

        ab = Pair.as_pair(ab, derivs)
        ab_wod = ab.wod

        #------------------------------------------
        # Make a rough initial guess
        #------------------------------------------
        pq = flat(ab_wod)
        pq.insert_deriv(dkey, Pair.IDENTITY)

        #------------------------------------------
        # Iterate until convergence...
        #------------------------------------------
        epsilon = 1.e-15
        for iter in range(self.iters):

            #- - - - - - - - - - - - - - - - - - - - - - - - - - - -
            # Evaluate the transform and its partial derivatives
            #- - - - - - - - - - - - - - - - - - - - - - - - - - - -
            ab0 = self._apply_polynomial(pq, coefft, 
                                                flat, derivs=True, from_=from_)
            dab_dpq = ab0.derivs[dkey]

            #- - - - - - - - - - - - - - - - - - - - - - - - - - - -
            # Apply one step of Newton's method in 2-D
            #- - - - - - - - - - - - - - - - - - - - - - - - - - - -
            dab = ab_wod - ab0.wod

            dpq_dab = dab_dpq.reciprocal()
            dpq = dpq_dab.chain(dab)
            pq += dpq

            #- - - - - - - - - - - - - - - - - - - - - - - - - - - -
            # Test for convergence
            #- - - - - - - - - - - - - - - - - - - - - - - - - - - -
            error_max = abs(dpq).max() / abs(pq).max()
            if Radial.DEBUG:
                print(iter, error_max)

            if error_max <= epsilon: break

        pq = pq.wod

        #------------------------------------------
        # Fill in derivatives if necessary
        #------------------------------------------
        pq.propagate_deriv(ab, dkey, dpq_dab, derivs)

        return pq
    #=========================================================================


#******************************************************************************



################################################################################
# UNIT TESTS
################################################################################

import unittest

class Test_Radial(unittest.TestCase):

    def runTest(self):

        Radial.DEBUG = True

        #====================================================================
        # Forward transform with uv_from_xy coefficients
        # Validate uv derivative propagation against central differences 
        # / chain rule
        #====================================================================
        xy_coefft = np.array([1.000, 
                              0, 
                             -5.9624209455667325e-08, 
                              0, 
                              2.7381910042256151e-14])

	scale = 0.00067540618
        shape = (1648,128)

        flat_fov = oops.fov.FlatFOV(scale, shape,  uv_los=(800,64), uv_area=1.)
        fov = Radial(scale, shape, coefft_uv_from_xy=xy_coefft, uv_los=(800,64), uv_area=1.)

        uv0 = Pair.combos(np.arange(100), np.arange(8)) * 16
        xy = flat_fov.xy_from_uv(uv0)
	xy.insert_deriv('t', Pair(np.random.randn(100,8,2)))
	xy.insert_deriv('ab', Pair(np.random.randn(100,8,2,2), drank=1))

        uv = fov.uv_from_xy(xy, derivs=True)
        embed()
	
        EPS = 1.e-5
        uv0 = fov.uv_from_xy(xy + (-EPS,0), False)
        uv1 = fov.uv_from_xy(xy + ( EPS,0), False)
        duv_dx = (uv1 - uv0) / (2. * EPS)

        uv0 = fov.uv_from_xy(xy + (0,-EPS), False)
        uv1 = fov.uv_from_xy(xy + (0, EPS), False)
        duv_dy = (uv1 - uv0) / (2. * EPS)

        duv_dt = duv_dx * xy.d_dt.vals[...,0] + duv_dy * xy.d_dt.vals[...,1]
        duv_da = duv_dx * xy.d_dab.vals[...,0,0] + duv_dy * xy.d_dab.vals[...,1,0]
        duv_db = duv_dx * xy.d_dab.vals[...,0,1] + duv_dy * xy.d_dab.vals[...,1,1]

        DEL = 1.e-6
        self.assertTrue(abs(uv.d_dt.vals - duv_dt.vals).max() <= DEL)
        self.assertTrue(abs(uv.d_dab.vals[...,0] - duv_da.vals).max() <= DEL)
        self.assertTrue(abs(uv.d_dab.vals[...,1] - duv_db.vals).max() <= DEL)

        self.assertTrue(abs(uv.d_dxy.vals[...,0,0] - duv_dx.vals[...,0]).max() <= DEL)
        self.assertTrue(abs(uv.d_dxy.vals[...,0,1] - duv_dy.vals[...,0]).max() <= DEL)
        self.assertTrue(abs(uv.d_dxy.vals[...,1,0] - duv_dx.vals[...,1]).max() <= DEL)
        self.assertTrue(abs(uv.d_dxy.vals[...,1,1] - duv_dy.vals[...,1]).max() <= DEL)








#        xy_from_uv_coefft = np.array([18318040., 
#                                     -36472916., 
#                                    -2432044., 
#                                     41065716., 
#                                     -20478757.])

#        uv = Pair.combos(np.arange(100), np.arange(8)) * 16
#	scale = 0.00067540618
	
#        fov = Radial(scale, uv.shape, coefft_xy_from_uv=xy_from_uv_coefft, uv_los=(800,64), uv_area=1.)

#        xy = fov.xy_from_uv(uv)
#        uv_test = fov.uv_from_xy(xy)
	
##        print(abs(uv - uv_test))
##        print(abs(uv - uv_test).max())
#        embed()

#        self.assertTrue(abs(uv - uv_test).max() < 1.e-14)








        #====================================================================
        # Forward vs. inverse transform with uv_from_xy coefficients,
        # no derivatives
        #====================================================================
        xy_coefft = np.array([1.000, 
                              0, 
                             -5.9624209455667325e-08, 
                              0, 
                              2.7381910042256151e-14])

	scale = 0.00067540618
        shape = (1648,128)

        flat_fov = oops.fov.FlatFOV(scale, shape,  uv_los=(800,64), uv_area=1.)
        fov = Radial(scale, shape, coefft_uv_from_xy=xy_coefft, uv_los=(800,64), uv_area=1.)

        uv0 = Pair.combos(np.arange(100), np.arange(8)) * 16
        xy = flat_fov.xy_from_uv(uv0)

        uv = fov.uv_from_xy(xy)
        xy_test = fov.xy_from_uv(uv)

#        self.assertTrue(abs(xy - xy_test).max() < 1.e-14)




        #====================================================================
        # Forward vs. inverse transform with uv_from_xy coefficients,
        # test derivative propagation
        #====================================================================
        xy_coefft = np.array([1.000, 
                              0, 
                             -5.9624209455667325e-08, 
                              0, 
                              2.7381910042256151e-14])

	scale = 0.00067540618
        shape = (1648,128)

        flat_fov = oops.fov.FlatFOV(scale, shape,  uv_los=(800,64), uv_area=1.)
        fov = Radial(scale, shape, coefft_uv_from_xy=xy_coefft, uv_los=(800,64), uv_area=1.)

        uv0 = Pair.combos(np.arange(100), np.arange(8)) * 16
        xy = flat_fov.xy_from_uv(uv0)
        xy.insert_deriv('t', Pair((1,1)))

        uv = fov.uv_from_xy(xy, derivs=True)
        xy_test = fov.xy_from_uv(uv, derivs=True)

        #-------------------------------
        # check derivative propagation
        #-------------------------------
        self.assertTrue('xy' in uv.derivs.keys())
        self.assertTrue('uv' in xy_test.derivs.keys())

        #------------------------------------
        # test self-derivatives in uv_test
        #------------------------------------
        dxy_dxy = xy_test.d_dxy.values
        dx_dx = dxy_dxy[...,0,0]
        dx_dy = dxy_dxy[...,0,1]
        dy_dy = dxy_dxy[...,1,1]
        dy_dx = dxy_dxy[...,1,0]

        EPS = 1.e-15
#        self.assertTrue(abs(dx_dx.max()-1) <= EPS)
#        self.assertTrue(abs(dx_dx.min()-1) <= EPS)

#        self.assertTrue(abs(dy_dy.max()-1) <= EPS)
#        self.assertTrue(abs(dy_dy.min()-1) <= EPS)

#        self.assertTrue(abs(dx_dy.max()) <= EPS)
#        self.assertTrue(abs(dy_dx.max()) <= EPS)



        #====================================================================
        # Forward vs. inverse transform with uv_from_xy coefficients
        # Verify that derivatives are not propagated for derivs=False
        #====================================================================
        xy_coefft = np.array([1.000, 
                              0, 
                             -5.9624209455667325e-08, 
                              0, 
                              2.7381910042256151e-14])

	scale = 0.00067540618
        shape = (1648,128)

        flat_fov = oops.fov.FlatFOV(scale, shape,  uv_los=(800,64), uv_area=1.)
        fov = Radial(scale, shape, coefft_uv_from_xy=xy_coefft, uv_los=(800,64), uv_area=1.)

        uv0 = Pair.combos(np.arange(100), np.arange(8)) * 16
        xy = flat_fov.xy_from_uv(uv0)
        xy.insert_deriv('t', Pair((1,1)))

        uv = fov.uv_from_xy(xy, derivs=False)
        self.assertEqual(uv.derivs, {})

        uv.insert_deriv('t', Pair((1,1)))
        xy_test = fov.xy_from_uv(uv, derivs=False)
        self.assertEqual(xy_test.derivs, {})



        return







        ############################
        uv_coefft = np.zeros((3,3,2))
        uv_coefft[...,0] = np.array([[ 5.000, -0.100, -0.001],
                                     [ 1.020, -0.001,  0.000],
                                     [-0.002,  0.000,  0.000]])
        uv_coefft[...,1] = np.array([[ 0.000, -1.010,  0.001],
                                     [-0.020, -0.003,  0.000],
                                     [-0.002,  0.000,  0.000]])

        uv = Pair.combos(np.arange(20), np.arange(15))

        fov = Polynomial(uv.shape, coefft_xy_from_uv=uv_coefft, uv_los=(7,7), uv_area=1.)

        xy = fov.xy_from_uv(uv)
        uv_test = fov.uv_from_xy(xy)

        self.assertTrue(abs(uv - uv_test).max() < 1.e-14)





        ############################
        uv_coefft = np.zeros((3,3,2))
        uv_coefft[...,0] = np.array([[ 5.00, -0.10, -0.01],
                                     [ 1.20, -0.01,  0.00],
                                     [-0.02,  0.00,  0.00]])
        uv_coefft[...,1] = np.array([[ 0.00, -1.10,  0.01],
                                     [-0.20, -0.03,  0.00],
                                     [-0.02,  0.00,  0.00]])

        uv = Pair.combos(np.arange(20), np.arange(15))
        uv.insert_deriv('t', Pair((1,1)))

        fov = Polynomial(uv.shape, coefft_xy_from_uv=uv_coefft, uv_los=(7,7), uv_area=1.)

        xy = fov.xy_from_uv(uv, derivs=False)
        self.assertEqual(xy.derivs, {})

        xy.insert_deriv('t', Pair((1,1)))
        uv_test = fov.uv_from_xy(xy, derivs=False)
        self.assertEqual(uv_test.derivs, {})

        self.assertTrue(abs(uv - uv_test).max() < 1.e-14)

        ############################
        uv_coefft = np.zeros((3,3,2))
        uv_coefft[...,0] = np.array([[ 5.00, -0.10, -0.01],
                                     [ 1.20, -0.01,  0.00],
                                     [-0.02,  0.00,  0.00]])
        uv_coefft[...,1] = np.array([[ 0.00, -1.10,  0.01],
                                     [-0.20, -0.03,  0.00],
                                     [-0.02,  0.00,  0.00]])

        uv = Pair.combos(np.arange(20), np.arange(15))
        uv.insert_deriv('t', Pair(np.random.randn(20,15,2)))
        uv.insert_deriv('ab', Pair(np.random.randn(20,15,2,2), drank=1))

        fov = Polynomial(uv.shape, coefft_xy_from_uv=uv_coefft, uv_los=(7,7), uv_area=1.)

        xy = fov.xy_from_uv(uv, derivs=True)

        EPS = 1.e-5
        xy0 = fov.xy_from_uv(uv + (-EPS,0), False)
        xy1 = fov.xy_from_uv(uv + ( EPS,0), False)
        dxy_du = (xy1 - xy0) / (2. * EPS)

        xy0 = fov.xy_from_uv(uv + (0,-EPS), False)
        xy1 = fov.xy_from_uv(uv + (0, EPS), False)
        dxy_dv = (xy1 - xy0) / (2. * EPS)

        dxy_dt = dxy_du * uv.d_dt.vals[...,0] + dxy_dv * uv.d_dt.vals[...,1]
        dxy_da = dxy_du * uv.d_dab.vals[...,0,0] + dxy_dv * uv.d_dab.vals[...,1,0]
        dxy_db = dxy_du * uv.d_dab.vals[...,0,1] + dxy_dv * uv.d_dab.vals[...,1,1]

        DEL = 1.e-6
        self.assertTrue(abs(xy.d_dt.vals - dxy_dt.vals).max() <= DEL)
        self.assertTrue(abs(xy.d_dab.vals[...,0] - dxy_da.vals).max() <= DEL)
        self.assertTrue(abs(xy.d_dab.vals[...,1] - dxy_db.vals).max() <= DEL)

        ############################
        uv_coefft = np.zeros((3,3,2))
        uv_coefft[...,0] = np.array([[ 5.00, -0.10, -0.01],
                                     [ 1.20, -0.01,  0.00],
                                     [-0.02,  0.00,  0.00]])
        uv_coefft[...,1] = np.array([[ 0.00, -1.10,  0.01],
                                     [-0.20, -0.03,  0.00],
                                     [-0.02,  0.00,  0.00]])

        uv = Pair.combos(np.arange(20), np.arange(15))
        fov = Polynomial(uv.shape, coefft_xy_from_uv=uv_coefft, uv_los=(7,7), uv_area=1.)

        xy = fov.xy_from_uv(uv, derivs=False)
        xy.insert_deriv('t', Pair(np.random.randn(20,15,2)))
        xy.insert_deriv('ab', Pair(np.random.randn(20,15,2,2), drank=1))

        uv = fov.uv_from_xy(xy, derivs=True)

        EPS = 1.e-5
        uv0 = fov.uv_from_xy(xy + (-EPS,0), False)
        uv1 = fov.uv_from_xy(xy + ( EPS,0), False)
        duv_dx = (uv1 - uv0) / (2. * EPS)

        uv0 = fov.uv_from_xy(xy + (0,-EPS), False)
        uv1 = fov.uv_from_xy(xy + (0, EPS), False)
        duv_dy = (uv1 - uv0) / (2. * EPS)

        duv_dt = duv_dx * xy.d_dt.vals[...,0] + duv_dy * xy.d_dt.vals[...,1]
        duv_da = duv_dx * xy.d_dab.vals[...,0,0] + duv_dy * xy.d_dab.vals[...,1,0]
        duv_db = duv_dx * xy.d_dab.vals[...,0,1] + duv_dy * xy.d_dab.vals[...,1,1]

        DEL = 1.e-6
        self.assertTrue(abs(uv.d_dt.vals - duv_dt.vals).max() <= DEL)
        self.assertTrue(abs(uv.d_dab.vals[...,0] - duv_da.vals).max() <= DEL)
        self.assertTrue(abs(uv.d_dab.vals[...,1] - duv_db.vals).max() <= DEL)

########################################
if __name__ == '__main__':
    unittest.main(verbosity=2)
################################################################################
