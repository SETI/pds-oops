################################################################################
# oops/surface/ellipsoid.py: Ellipsoid subclass of class Surface
################################################################################

import numpy as np
from polymath     import Matrix, Scalar, Vector3
from oops.config  import SURFACE_PHOTONS, LOGGING
from oops.frame   import Frame
from oops.path    import Path
from oops.surface import Surface

class Ellipsoid(Surface):
    """An ellipsoidal surface centered on the given path and fixed with respect
    to the given frame. The short radius of the ellipsoid is oriented along the
    Z-axis of the frame and the long radius is along the X-axis.

    The coordinates defining the surface grid are (longitude, latitude).
    Both are based on the assumption that a spherical body has been "squashed"
    along the Y- and Z-axes. The latitudes and longitudes defined in this manner
    are neither planetocentric nor planetographic; functions are provided to
    perform conversions to either choice. Longitudes are measured in a right-
    handed manner, increasing toward the east; values range from 0 to 2*pi.

    The third coordinate is z, which measures vertical distance in km along the
    normal vector from the surface.
    """

    COORDINATE_TYPE = 'spherical'
    IS_VIRTUAL = False
    HAS_INTERIOR = True

    DEBUG = False       # True for convergence testing in intercept_normal_to()

    #===========================================================================
    def __init__(self, origin, frame, radii, exclusion=0.9):
        """Constructor for an Ellipsoid object.

        Input:
            origin      the Path object or ID defining the center of the
                        ellipsoid.
            frame       the Frame object or ID defining the coordinate frame in
                        which the ellipsoid is fixed, with the shortest radius
                        of the ellipsoid along the Z-axis and the longest radius
                        along the X-axis.
            radii       a tuple (a,b,c) containing the radii from longest to
                        shortest, in km.
            exclusion   the fraction of the polar radius within which
                        calculations of intercept_normal_to() are suppressed.
                        Values of less than 0.95 are not recommended because
                        the problem becomes numerically unstable.
        """

        self.origin = Path.as_waypoint(origin)
        self.frame  = Frame.as_wayframe(frame)

        self.radii    = np.asfarray(radii)
        self.radii_sq = self.radii**2
        self.req      = self.radii[0]
        self.req_sq   = self.req**2
        self.rpol     = self.radii[2]

        self.squash_y       = self.radii[1] / self.radii[0]
        self.squash_y_sq    = self.squash_y**2
        self.unsquash_y     = self.radii[0] / self.radii[1]
        self.unsquash_y_sq  = self.unsquash_y**2

        self.squash_z       = self.radii[2] / self.radii[0]
        self.squash_z_sq    = self.squash_z**2
        self.unsquash_z     = self.radii[0] / self.radii[2]
        self.unsquash_z_sq  = self.unsquash_z**2

        self.squash         = Vector3((1., self.squash_y, self.squash_z))
        self.squash_sq      = self.squash.element_mul(self.squash)
        self.unsquash       = Vector3((1., 1./self.squash_y, 1./self.squash_z))
        self.unsquash_sq    = self.unsquash.element_mul(self.unsquash)

        self.unsquash_sq_2d = Matrix(([1.,0.,0.],
                                      [0.,self.unsquash_y**2,0.],
                                      [0.,0.,self.unsquash_z**2]))

        # This is the exclusion zone radius, within which calculations of
        # intercept_normal_to() are automatically masked due to the ill-defined
        # geometry.
        self.exclusion = float(exclusion)
        self.r_exclusion = self.req * self.exclusion

        self.unmasked = self

        # Unique key for intercept calculations
        self.intercept_key = ('ellipsoid', self.origin.waypoint,
                                           self.frame.wayframe,
                                           tuple(self.radii),
                                           self.exclusion)

    def __getstate__(self):
        return (Path.as_primary_path(self.origin),
                Frame.as_primary_frame(self.frame),
                tuple(self.radii), self.exclusion)

    def __setstate__(self, state):
        self.__init__(*state)

    #===========================================================================
    def coords_from_vector3(self, pos, obs=None, time=None, axes=2,
                                  derivs=False, hints=None, groundtrack=False):
        """Surface coordinates associated with a position vector.

        Input:
            pos         a Vector3 of positions at or near the surface, relative
                        to this surface's origin and frame.
            obs         a Vector3 of observer position relative to this
                        surface's origin and frame; ignored here.
            time        a Scalar time at which to evaluate the surface; ignored.
            axes        2 or 3, indicating whether to return a tuple of two or
                        three Scalar objects.
            derivs      True to propagate any derivatives inside pos and obs
                        into the returned coordinates.
            hints       if provided, the value of the coefficient p such that
                            ground + p * normal(ground) = pos
                        for the ground point on the body surface.
            groundtrack True to return the intercept on the surface along with
                        the coordinates.

        Return:         a tuple of two to four items:
            lon         longitude at the surface in radians.
            lat         latitude at the surface in radians.
            z           vertical altitude in km normal to the surface; included
                        if axes == 3.
            groundtrack intecept point on the surface (where z == 0); included
                        if input groundtrack is True.
        """

        # Validate inputs
        self._coords_from_vector3_check(axes)

        pos = Vector3.as_vector3(pos, recursive=derivs)

        # Use the quick solution for the body points if hints are provided
        if hints is not None:
            p = Scalar.as_scalar(hints, recursive=derivs)
            denom = Vector3.ONES + p * self.unsquash_sq
            track = pos.element_div(denom)
        else:
            (track, p) = self.intercept_normal_to(pos, guess=True)

        # Derive the coordinates
        track_unsquashed = track.element_mul(self.unsquash)
        (x,y,z) = track_unsquashed.to_scalars()
        lat = (z/self.req).arcsin()
        lon = y.arctan2(x) % Scalar.TWOPI

        results = (lon, lat)

        if axes == 3:
            r = (pos - track).norm() * p.sign()
            results += (r,)

        if groundtrack:
            results += (track,)

        return results

    #===========================================================================
    def vector3_from_coords(self, coords, obs=None, time=None, derivs=False,
                                          groundtrack=False):
        """The position where a point with the given coordinates falls relative
        to this surface's origin and frame.

        Input:
            coords      a tuple of two or three Scalars defining coordinates at
                        or near this surface.
                lon     longitude at the surface in radians.
                lat     latitude at the surface in radians.
                z       vertical altitude in km normal to the body surface.
            obs         a Vector3 of observer position relative to this
                        surface's origin and frame; ignored here.
            time        a Scalar time at which to evaluate the surface; ignored.
            derivs      True to propagate any derivatives inside the coordinates
                        and obs into the returned position vectors.
            groundtrack True to include the associated groundtrack points on the
                        body surface in the returned result.

        Return:         pos or (pos, groundtrack), where
            pos         a Vector3 of points defined by the coordinates, relative
                        to this surface's origin and frame.
            groundtrack True to include the associated groundtrack points on the
                        body surface in the returned result.

        Note that the coordinates can all have different shapes, but they must
        be broadcastable to a single shape.
        """

        # Validate inputs
        self._vector3_from_coords_check(coords)

        # Determine groundtrack
        lon = Scalar.as_scalar(coords[0], derivs)
        lat = Scalar.as_scalar(coords[1], derivs)
        track_unsquashed = Vector3.from_ra_dec_length(lon, lat, self.req)
        track = track_unsquashed.element_mul(self.squash)

        # Assemble results
        if len(coords) == 2:
            results = (track, track)

        else:
            # Add the z-component
            normal = self.normal(track)
            results = (track + (coords[2] / normal.norm()) * normal, track)

        if groundtrack:
            return results

        return results[0]

    #===========================================================================
    def position_is_inside(self, pos, obs=None, time=None):
        """Where positions are inside the surface.

        Input:
            pos         a Vector3 of positions at or near the surface relative
                        to this surface's origin and frame.
            obs         observer position as a Vector3 relative to this
                        surface's origin and frame. Ignored for solid surfaces.
            time        a Scalar time at which to evaluate the surface; ignored
                        unless the surface is time-variable.

        Return:         Boolean True where positions are inside the surface
        """

        unsquashed = Vector3.as_vector3(pos).element_mul(self.unsquash)
        return unsquashed.norm() < self.radii[0]

    #===========================================================================
    def intercept(self, obs, los, time=None, direction='dep', derivs=False,
                                  guess=None, hints=None):
        """The position where a specified line of sight intercepts the surface.

        Input:
            obs         observer position as a Vector3 relative to this
                        surface's origin and frame.
            los         line of sight as a Vector3 in this surface's frame.
            time        a Scalar time at the surface; ignored.
            direction   'arr' for a photon arriving at the surface; 'dep' for a
                        photon departing from the surface.
            derivs      True to propagate any derivatives inside obs and los
                        into the returned intercept point.
            guess       unused.
            hints       unused.

        Return:         a tuple (pos, t) where
            pos         a Vector3 of intercept points on the surface relative
                        to this surface's origin and frame, in km.
            t           a Scalar such that:
                            intercept = obs + t * los
        """

        # Convert to Vector3 and un-squash
        obs = Vector3.as_vector3(obs, recursive=derivs)
        los = Vector3.as_vector3(los, recursive=derivs)

        obs_unsquashed = obs.element_mul(self.unsquash)
        los_unsquashed = los.element_mul(self.unsquash)

        # Solve for the intercept distance, masking lines of sight that miss
        #   pos = obs + t * los
        #   pos**2 = radius**2 [after "unsquash"]
        #
        # dot(obs,obs) + 2 * t * dot(obs,los) + t**2 * dot(los,los) = radius**2
        #
        # Use the quadratic formula to solve for t...
        #
        # a = los_unsquashed.dot(los_unsquashed)
        # b = los_unsquashed.dot(obs_unsquashed) * 2.
        # c = obs_unsquashed.dot(obs_unsquashed) - self.req_sq
        # d = b**2 - 4. * a * c
        #
        # Case 1: For photons departing from the surface and arriving at the
        # observer, we expect b > 0 (because dot(los,obs) must be positive for a
        # solution to exist) and we expect t < 0 (for an earlier time). In this
        # case, we seek the greater value of t, which corresponds to the surface
        # point closest to the observer.
        #
        # Case 2: For photons arriving at the surface, we expect b < 0 and
        # t > 0. In this case, we seek the lesser value of t, corresponding to
        # the point on the surface facing the source.
        #
        # However, also note that we need this method to work correctly even for
        # observers located "inside" the surface (where c < 0). This case is not
        # physical, but it can occur during iterations of _solve_photon_by_los.
        #
        # Case 1: If c < 0, we still seek the lesser value of t, but it will be
        # positive. In summary:
        #   t = (-b + sqrt(d)) / (2*a)
        # (because a is always positive) or, equivalently
        #   t = (-2*c) / (b + sqrt(d))
        # Of these two options, the second is preferred because, when outside
        # the body, it avoids the partial cancellation of -b and sqrt(d).
        #
        # Case 2: If c < 0, we still seek the greater value of t, but it will
        # be negative. In summary:
        #   t = (-b + sqrt(d)) / (2*a)
        # This is the preferred solution, because b and sqrt(d) usually have
        # opposite signs, so they generally do not cancel.

        # This is the same formula as above, but avoids a few multiplies by 2
        a      = los_unsquashed.dot(los_unsquashed)
        b_div2 = los_unsquashed.dot(obs_unsquashed)
        c      = obs_unsquashed.dot(obs_unsquashed) - self.req_sq
        d_div4 = b_div2**2 - a * c

        if direction == 'dep':                  # Case 1
            t = -c / (b_div2 + d_div4.sqrt())
        else:                                   # Case 2
            t = (d_div4.sqrt() - b_div2) / a

        pos = obs + t*los

        if hints is not None:
            return (pos, t, hints)

        return (pos, t)

    #===========================================================================
    def normal(self, pos, time=None, derivs=False):
        """The normal vector at a position at or near a surface.

        Input:
            pos         a Vector3 of positions at or near the surface relative
                        to this surface's origin and frame.
            time        a Scalar time at which to evaluate the surface; ignored.
            derivs      True to propagate any derivatives of pos into the
                        returned normal vectors.

        Return:         a Vector3 containing directions normal to the surface
                        that pass through the position. Lengths are arbitrary.
        """

        pos = Vector3.as_vector3(pos, derivs)
        return pos.element_mul(self.unsquash_sq)

    #===========================================================================
    def intercept_with_normal(self, normal, time=None, direction='dep',
                                            derivs=False, guess=None):
        """Intercept point where the normal vector parallels the given vector.

        Input:
            normal      a Vector3 of normal vectors in this surface's frame.
            time        a Scalar time at which to evaluate the surface; ignored.
            direction   'arr' for a photon arriving at the surface; 'dep' for a
                        photon departing from the surface.
            derivs      True to propagate derivatives in the normal vector into
                        the returned intercepts.
            guess       optional initial guess a coefficient array p such that:
                            pos = intercept + p * normal(intercept)
                        Use guess=False for the converged value of p to be
                        returned even if an initial guess was not provided.

        Return:         a Vector3 of surface intercept points, in km. Where no
                        solution exists, the returned Vector3 will be masked.
        """

        normal = Vector3.as_vector3(normal, derivs)
        return normal.element_mul(self.squash).unit().element_mul(self.radii)

    #===========================================================================
    def intercept_normal_to(self, pos, time=None, direction='dep', derivs=False,
                                       guess=None):
        """Intercept point whose normal vector passes through a given position.

        Input:
            pos         a Vector3 of positions at or near the surface relative
                        to this surface's origin and frame.
            time        a Scalar time at the surface; ignored here.
            direction   'arr' for a photon arriving at the surface; 'dep' for a
                        photon departing from the surface; ignored here.
            derivs      True to propagate derivatives in pos into the returned
                        intercepts.
            guess       optional initial guess a coefficient array p such that:
                            intercept + p * normal(intercept) = pos
                        Use guess=True for the converged value of p to be
                        returned even if an initial guess was not provided.

        Return:         intercept or (intercept, p)
            intercept   a vector3 of surface intercept points relative to this
                        surface's origin and frame, in km. Where no intercept
                        exists, the returned vector will be masked.
            p           the converged solution such that
                            intercept = pos + p * normal(intercept);
                        included if guess is not None.
        """

        pos = Vector3.as_vector3(pos, recursive=derivs)
        pos = self._apply_exclusion(pos)

        # We need to solve for p such that:
        #   cept + p * normal(cept) = pos
        # where
        #   normal(cept) = cept.element_mul(self.unsquash_sq)
        #
        # This is subject to the constraint that cept is the intercept point on
        # the surface, where
        #   cept_unsquashed = cept.element_mul(self.unsquash)
        # and
        #   cept_unsquashed.dot(cept_unsquashed) = self.req_sq
        #
        # Let:

        B = self.unsquash_y_sq
        C = self.unsquash_z_sq
        R = self.req_sq

        # Four equations with four unknowns:
        # cept_x + p * cept_x = pos_x
        # cept_y + p * cept_y * B = pos_y
        # cept_z + p * cept_z * C = pos_z
        # cept_x**2 + cept_y**2 * B + cept_z**2 * C = R
        #
        # Let:

        (pos_x, pos_y, pos_z) = pos.to_scalars()
        X = pos_x**2
        Y = pos_y**2 * B
        Z = pos_z**2 * C

        # Plug the first three into the fourth and rearrange:
        #
        # f(p) = (  X * ((1 + B*p) * (1 + C*p))**2
        #         + Y * ((1 + p) * (1 + C*p))**2
        #         + Z * ((1 + p) * (1 + B*p))**2
        #         - R * ((1 + p) * (1 + B*p) * (1 + C*p))**2)
        #
        # This is a sixth-order polynomial, which we need to solve for f(p) = 0.
        #
        # Using SymPy, this expands to:
        #
        # f(p) = -B**2*C**2*R*p**6
        #      + p**5*(-2*B**2*C**2*R - 2*B**2*C*R - 2*B*C**2*R)
        #      + p**4*(-B**2*C**2*R + B**2*C**2*X - 4*B**2*C*R - B**2*R
        #              + B**2*Z - 4*B*C**2*R - 4*B*C*R - C**2*R + C**2*Y)
        #      + p**3*(-2*B**2*C*R + 2*B**2*C*X - 2*B**2*R + 2*B**2*Z
        #              - 2*B*C**2*R + 2*B*C**2*X - 8*B*C*R - 2*B*R + 2*B*Z
        #              - 2*C**2*R + 2*C**2*Y - 2*C*R + 2*C*Y)
        #      + p**2*(-B**2*R + B**2*X + B**2*Z - 4*B*C*R + 4*B*C*X - 4*B*R
        #              + 4*B*Z - C**2*R + C**2*X + C**2*Y - 4*C*R + 4*C*Y - R
        #              + Y + Z)
        #      + p*(-2*B*R + 2*B*X + 2*B*Z - 2*C*R + 2*C*X + 2*C*Y - 2*R + 2*Y
        #           + 2*Z)
        #      - R + X + Y + Z
        #
        # Let f(p) = (((((f6*p + f5)*p + f4)*p + f3)*p + f2)*p + f1)*p + f0

        B2 = B**2
        C2 = C**2

        # For efficiency, we segregate all the array ops (involving X, Y, Z)
        f6 = -B2 * C2 * R
        f5 = -2 * R * (B2*C2 + B2*C + B*C2)
        f4 = (X * (B2*C2) + Y * C2 + Z * B2
              - R * (B2*C2 + 4*B2*C + 4*B*C2 + 4*B*C + B2 + C2))
        f3 = (X * (2*(B2*C + B*C2)) + Y * (2*(C2 + C)) + Z * (2*(B2 + B))
              - 2 * R * (B2*C + B*C2 + 4*B*C + B2 + C2 + B + C))
        f2 = (X * (B2 + 4*B*C + C2) + Y * (C2 + 4*C + 1) + Z * (B2 + 4*B + 1)
              - R * (B2 + 4*B*C + C2 + 4*B + 4*C + 1))
        f1 = (X * (2*B + 2*C) + Y * (2*C + 2) + Z * (2*B + 2)
              - 2 * R * (B + C + 1))
        f0 = X + Y + Z - R

        g5 = 6 * f6
        g4 = 5 * f5
        g3 = 4 * f4
        g2 = 3 * f3
        g1 = 2 * f2
        g0 = f1

        # Make an initial guess at p
        if guess in (None, True):

            # Unsquash into coordinates where the surface is a sphere
            pos_unsq = pos.wod.element_mul(self.unsquash)   # without derivs!

            # Estimate the intercept point as on a straight line to the origin
            # (Note that this estimate is exact for points at the surface.)
            cept_guess_unsq = pos_unsq.with_norm(self.req)

            # Make a guess at the normal vector in unsquashed coordinates
            normal_guess_unsq = cept_guess_unsq.element_mul(self.unsquash_sq)

            # Estimate p for [cept + p * normal(cept) = pos] using norms
            p = ((pos_unsq.norm() - cept_guess_unsq.norm())
                 / normal_guess_unsq.norm())

        else:
            p = guess.wod.copy()

        # The precision of p should match the default geometric accuracy defined
        # by SURFACE_PHOTONS.km_precision. Set our precision goal on p
        # accordingly.
        km_scale = self.req
        precision = SURFACE_PHOTONS.km_precision / km_scale

        # Iterate until convergence stops
        max_dp = 1.e99
        converged = False

        # We typically need a few extra iterations to reach desired precision
        for count in range(SURFACE_PHOTONS.max_iterations + 10):

            # Calculate f and df/dp
            f = (((((f6*p + f5)*p + f4)*p + f3)*p + f2)*p + f1)*p + f0
            df_dp = ((((g5*p + g4)*p + g3)*p + g2)*p + g1)*p + g0

            # One step of Newton's method
            dp = f / df_dp
            p -= dp

            prev_max_dp = max_dp
            max_dp = dp.abs().max(builtins=True, masked=-1.)

            if LOGGING.surface_iterations or Ellipsoid.DEBUG:
                LOGGING.convergence(
                            '%s.intercept_normal_to(): iter=%d; change[km]=%.6g'
                            % (type(self).__name__, count+1, max_dp * km_scale))

            if max_dp <= precision:
                converged = True
                break

            if max_dp >= prev_max_dp:
                break

        if not converged:
            LOGGING.warn('%s.intercept_normal_to() did not converge: '
                         'iter=%d; change[km]=%.6g'
                         % (type(self).__name__, count+1, max_dp * km_scale))

        cept_x = pos_x / (1 + p)
        cept_y = pos_y / (1 + B * p)
        cept_z = pos_z / (1 + C * p)
        cept = Vector3.from_scalars(cept_x, cept_y, cept_z)

        if guess is None:
            return cept
        else:
            return (cept, p)

    #===========================================================================
    def _apply_exclusion(self, pos):
        """This internal method is used by intercept_normal_to() to exclude any
        positions that fall too close to the center of the surface. The math
        is poorly-behaved in this region.

        (1) It sets the mask on any of these points to True.
        (2) It sets the magnitude of any of these points to the edge of the
            exclusion zone, in order to avoid runtime errors in the math
            libraries.
        """

        pos_unsquashed = pos.element_mul(self.unsquash)
        norm_sq = pos_unsquashed.wod.norm_sq()
        mask = (norm_sq < self.r_exclusion**2)
        if not mask.any():
            return pos

        rescale = Scalar.maximum(1., self.r_exclusion / norm_sq.sqrt())
        return (pos * rescale).remask_or(mask)

    ############################################################################
    # Longitude conversions
    ############################################################################

    def lon_to_centric(self, lon, derivs=False):
        """Convert longitude in internal coordinates to planetocentric.

        Input:
            lon         squashed longitude in radians.
            derivs      True to include derivatives in returned result.

        Return          planetocentric longitude.
        """

        lon = Scalar.as_scalar(lon, recursive=derivs)
        return (lon.sin() * self.squash_y).arctan2(lon.cos())

    #===========================================================================
    def lon_from_centric(self, lon, derivs=False):
        """Convert planetocentric longitude to internal coordinates.

        Input:
            lon         planetocentric longitude in radians.
            derivs      True to include derivatives in returned result.

        Return          squashed longitude.
        """

        lon = Scalar.as_scalar(lon, recursive=derivs)
        return (lon.sin() * self.unsquash_y).arctan2(lon.cos())

    #===========================================================================
    def lon_to_graphic(self, lon, derivs=False):
        """Convert longitude in internal coordinates to planetographic.

        Input:
            lon         squashed longitude in radians.
            derivs      True to include derivatives in returned result.

        Return          planetographic longitude.
        """

        lon = Scalar.as_scalar(lon, recursive=derivs)
        return (lon.sin() * self.unsquash_y).arctan2(lon.cos())

    #===========================================================================
    def lon_from_graphic(self, lon, derivs=False):
        """Convert planetographic longitude to internal coordinates.

        Input:
            lon         planetographic longitude in radians.
            derivs      True to include derivatives in returned result.

        Return          squashed longitude.
        """

        lon = Scalar.as_scalar(lon, recursive=derivs)
        return (lon.sin() * self.squash_y).arctan2(lon.cos())

    ############################################################################
    # Latitude conversions
    ############################################################################

    def lat_to_centric(self, lat, lon, derivs=False):
        """Convert latitude in internal ellipsoid coordinates to planetocentric.

        Input:
            lat         squashed latitide, radians.
            lon         squashed longitude, radians.
            derivs      True to include derivatives in returned result.

        Return          planetocentric latitude.
        """

        lon = Scalar.as_scalar(lon, recursive=derivs)
        lat = Scalar.as_scalar(lat, recursive=derivs)

        denom = (lon.cos()**2 + (lon.sin() * self.squash_y)**2).sqrt()

        return (lat.tan() * self.squash_z / denom).arctan()

    #===========================================================================
    def lat_from_centric(self, lat, lon, derivs=False):
        """Convert planetocentric latitude to internal ellipsoid latitude.

        Input:
            lat         planetocentric latitide, radians.
            lon         planetocentric longitude, radians.
            derivs      True to include derivatives in returned result.

        Return          squashed latitude.
        """

        lon = Scalar.as_scalar(lon, recursive=derivs)
        lat = Scalar.as_scalar(lat, recursive=derivs)

        factor = (lon.cos()**2 + (lon.sin() * self.squash_y)**2).sqrt()

        return (lat.tan() * self.unsquash_z * factor).arctan()

    #===========================================================================
    def lat_to_graphic(self, lat, lon, derivs=False):
        """Convert latitude in internal ellipsoid coordinates to planetographic.

        Input:
            lat         squashed latitide, radians.
            lon         squashed longitude, radians.
            derivs      True to include derivatives in returned result.

        Return          planetographic latitude.
        """

        lon = Scalar.as_scalar(lon, recursive=derivs)
        lat = Scalar.as_scalar(lat, recursive=derivs)

        denom = (lon.cos()**2 + (lon.sin() * self.unsquash_y)**2).sqrt()

        return (lat.tan() * self.unsquash_z / denom).arctan()

    #===========================================================================
    def lat_from_graphic(self, lat, lon, derivs=False):
        """Convert a planetographic latitude to internal ellipsoid latitude.

        Input:
            lat         planetographic latitide, radians.
            lon         planetographic longitude, radians.
            derivs      True to include derivatives in returned result.

        Return          squashed latitude.
        """

        lon = Scalar.as_scalar(lon, recursive=derivs)
        lat = Scalar.as_scalar(lat, recursive=derivs)

        factor = (lon.cos()**2 + (lon.sin() * self.unsquash_y)**2).sqrt()

        return (lat.tan() * self.squash_z * factor).arctan()

################################################################################
# UNIT TESTS
################################################################################

import unittest

class Test_Ellipsoid(unittest.TestCase):

    def runTest(self):

        np.random.seed(2610)

        REQ  = 60268.
        RMID = 54364.
        RPOL = 50000.
        planet = Ellipsoid('SSB', 'J2000', (REQ, RMID, RPOL))

        # Coordinate/vector conversions
        NPTS = 10000

        lon = Scalar(np.random.rand(NPTS) * Scalar.TWOPI)
        lat = Scalar(np.random.rand(NPTS) * Scalar.PI - Scalar.HALFPI)
        track = planet.vector3_from_coords((lon,lat))
        (lon2, lat2) = planet.coords_from_vector3(track, axes=2)
        self.assertTrue((lon - lon2).abs().max() < 1.e-15)
        self.assertTrue((lat - lat2).abs().max() < 1.e-11)

        track2 = planet.vector3_from_coords((lon2,lat2))
        self.assertTrue((track2 - track).norm() < 1.e-6)

        lon = Scalar(np.random.rand(NPTS) * Scalar.TWOPI)
        lat = Scalar(np.random.rand(NPTS) * Scalar.PI - Scalar.HALFPI)
        z = Scalar(np.random.rand(NPTS) * 1000.)
        test = planet.vector3_from_coords((lon,lat,z))
        track = planet.vector3_from_coords((lon,lat))
        diff = test - track
        self.assertTrue((diff.norm()).abs() - z < 3.e-11)
        self.assertTrue(diff.sep(planet.normal(track)).max() < 1.e-10)

        (lon2, lat2, z2) = planet.coords_from_vector3(test, axes=3)
        (lon3, lat3, z3) = planet.coords_from_vector3(track, axes=3)
        self.assertTrue((lon - lon2).abs().max() < 1.e-15)
        self.assertTrue((lat - lat2).abs().max() < 3.e-12)
        self.assertTrue((lon3 - lon2).abs().max() < 1.e-15)
        self.assertTrue((lat3 - lat2).abs().max() < 1.e-11)
        self.assertTrue(z3.abs().max() < 1.e-10)
        self.assertTrue((z2 - z).abs().max() < 1.e-10)

        (_, track1) = planet.vector3_from_coords((lon,lat,z), groundtrack=True)
        (_, _, track2) = planet.coords_from_vector3(test, axes=2, groundtrack=True)
        self.assertTrue((track1 - track2).norm().max() < 1.e-10)

        pos = (2 * np.random.rand(NPTS,3) - 1.) * REQ   # range is -REQ to REQ

        (lon,lat,elev,track) = planet.coords_from_vector3(pos, axes=3, groundtrack=True)
        test = planet.vector3_from_coords((lon,lat,elev))
        self.assertTrue((test - pos).norm().max() < 1.e-8)

        # Make sure longitudes convert to planetocentric and back
        test_lon = np.arctan2(track.vals[...,1], track.vals[...,0]) % Scalar.TWOPI
        centric_lon = planet.lon_to_centric(lon)
        diffs = (centric_lon - test_lon + Scalar.HALFPI) % Scalar.PI - Scalar.HALFPI
        self.assertTrue((diffs).abs().max() < 1.e-8)

        test_lon2 = planet.lon_from_centric(centric_lon)
        diffs = (test_lon2 - lon + Scalar.HALFPI) % Scalar.PI - Scalar.HALFPI
        self.assertTrue((diffs).abs().max() < 1.e-8)

        # Make sure latitudes convert to planetocentric and back
        test_lat = np.arcsin(track.vals[...,2] / np.sqrt(np.sum(track.vals**2, axis=-1)))
        centric_lat = planet.lat_to_centric(lat,lon)
        self.assertTrue(abs(centric_lat - test_lat).max() < 1.e-8)

        test_lat2 = planet.lat_from_centric(centric_lat, lon)
        self.assertTrue(abs(test_lat2 - lat).max() < 1.e-8)

        # Make sure longitudes convert to planetographic and back
        normals = planet.normal(track)
        test_lon = np.arctan2(normals.vals[...,1], normals.vals[...,0])
        graphic_lon = planet.lon_to_graphic(lon)
        diffs = (graphic_lon - test_lon + Scalar.HALFPI) % Scalar.PI - Scalar.HALFPI
        self.assertTrue(abs(diffs).max() < 1.e-8)

        test_lon2 = planet.lon_from_centric(centric_lon)
        diffs = (test_lon2 - lon + Scalar.HALFPI) % Scalar.PI - Scalar.HALFPI
        self.assertTrue(abs(diffs).max() < 1.e-8)

        # Make sure latitudes convert to planetographic and back
        test_lat = np.arcsin(normals.vals[...,2] / normals.norm().vals)
        graphic_lat = planet.lat_to_graphic(lat,lon)
        self.assertTrue(abs(graphic_lat - test_lat).max() < 1.e-8)

        test_lat2 = planet.lat_from_graphic(graphic_lat, lon)
        self.assertTrue(abs(test_lat2 - lat).max() < 1.e-8)

        # Ellipsoid intercepts & normals
        obs = REQ * (np.random.rand(NPTS,3) + 1.)       # range is REQ to 2*REQ
        los = -np.random.rand(NPTS,3)                   # range is -1 to 0

        (pts, t) = planet.intercept(obs, los)
        test = t * Vector3(los) + Vector3(obs)
        self.assertTrue(abs(test - pts).max() < 1.e-9)

        self.assertTrue(np.all(t.mask == pts.mask))
        self.assertTrue(np.all(pts.mask[t.vals < 0.]))

        normals = planet.normal(pts)

        pts.vals[...,1] *= REQ/RMID
        pts.vals[...,2] *= REQ/RPOL
        self.assertTrue(abs(pts.norm() - REQ).max() < 1.e-8)

        normals.vals[...,1] *= RMID/REQ
        normals.vals[...,2] *= RPOL/REQ
        self.assertTrue(abs(normals.unit() - pts.unit()).max() < 1.e-14)

        # Intercept derivatives

        # Lines of sight with grazing incidence can have large numerical errors,
        # but this is not to be considered an error in the analytic calculation.
        # As a unit test, we ignore the largest 3% of the errors, but require
        # that the rest of the errors be very small.

        obs = REQ * (np.random.rand(NPTS,3) + 1.)       # range is REQ to 2*REQ
        los = -np.random.rand(NPTS,3)                   # range is -1 to 0

        obs = Vector3(obs)
        los = Vector3(los).unit()
        obs.insert_deriv('obs', Vector3.IDENTITY)
        los.insert_deriv('los', Vector3.IDENTITY)

        eps = 1.
        frac = 0.97     # Ignore errors above this cutoff
        dobs = ((eps,0,0), (0,eps,0), (0,0,eps))
        for i in range(3):
            (cept,t) = planet.intercept(obs, los, derivs=True)
            (cept1,t1) = planet.intercept(obs + dobs[i], los, derivs=False)
            (cept2,t2) = planet.intercept(obs - dobs[i], los, derivs=False)

            dcept_dobs = (cept1 - cept2) / (2*eps)
            ref = Vector3(cept.d_dobs.vals[...,i], cept.d_dobs.mask)

            errors = abs(dcept_dobs - ref) / abs(ref)
            sorted = np.sort(errors.vals[errors.antimask])
                        # mask=True where the line of sight missed the surface
            selected_error = sorted[int(sorted.size * frac)]
            self.assertTrue(selected_error < 1.e-5)

            dt_dobs = (t1 - t2) / (2*eps)
            ref = t.d_dobs.vals[...,i]

            errors = abs(dt_dobs/ref - 1)
            sorted = np.sort(errors.vals[errors.antimask])
            selected_error = sorted[int(sorted.size * frac)]
            self.assertTrue(selected_error < 1.e-5)

        eps = 1.e-6
        frac = 0.97
        dlos = ((eps,0,0), (0,eps,0), (0,0,eps))
        for i in range(3):
            (cept,t) = planet.intercept(obs, los, derivs=True)
            (cept1,t1) = planet.intercept(obs, los + dlos[i], derivs=False)
            (cept2,t2) = planet.intercept(obs, los - dlos[i], derivs=False)

            dcept_dlos = (cept1 - cept2) / (2*eps)
            ref = Vector3(cept.d_dlos.vals[...,i], cept.d_dlos.mask)

            errors = abs(dcept_dlos - ref) / abs(ref)
            sorted = np.sort(errors.vals[errors.antimask])
            selected_error = sorted[int(sorted.size * frac)]
            self.assertTrue(selected_error < 1.e-5)

            dt_dlos = (t1 - t2) / (2*eps)
            ref = t.d_dlos.vals[...,i]

            errors = abs(dt_dlos/ref - 1)
            sorted = np.sort(errors.vals[errors.antimask])
            selected_error = sorted[int(sorted.size * frac)]
            self.assertTrue(selected_error < 1.e-5)

        # Test normal()
        cept = Vector3(np.random.random((100,3))).unit().element_mul(planet.radii)
        perp = planet.normal(cept)
        test1 = cept.element_mul(planet.unsquash).unit()
        test2 = perp.element_mul(planet.squash).unit()

        self.assertTrue(abs(test1 - test2).max() < 1.e-12)

        eps = 1.e-7
        (lon,lat) = planet.coords_from_vector3(cept, axes=2)
        cept1 = planet.vector3_from_coords((lon+eps,lat,0.))
        cept2 = planet.vector3_from_coords((lon-eps,lat,0.))

        self.assertTrue(abs((cept2 - cept1).sep(perp) - Scalar.HALFPI).max() < 1.e-8)

        (lon,lat) = planet.coords_from_vector3(cept, axes=2)
        cept1 = planet.vector3_from_coords((lon,lat+eps,0.))
        cept2 = planet.vector3_from_coords((lon,lat-eps,0.))

        self.assertTrue(abs((cept2 - cept1).sep(perp) - Scalar.HALFPI).max() < 1.e-8)

        # Test intercept_with_normal()
        vector = Vector3(np.random.random((100,3)))
        cept = planet.intercept_with_normal(vector)
        sep = vector.sep(planet.normal(cept))
        self.assertTrue(sep.max() < 1.e-14)

        # Test intercept_normal_to()
        pos = Vector3(np.random.random((100,3)) * 4.*REQ + REQ)
        cept = planet.intercept_normal_to(pos)
        sep = (pos - cept).sep(planet.normal(cept))
        self.assertTrue(sep.max() < 3.e-12)
        self.assertTrue(abs(cept.element_mul(planet.unsquash).norm() -
                        planet.req).max() < 1.e-6)

        # Test normal() derivative
        cept = Vector3(np.random.random((100,3))).unit().element_mul(planet.radii)
        cept.insert_deriv('pos', Vector3.IDENTITY, override=True)
        perp = planet.normal(cept, derivs=True)
        eps = 1.e-5
        dpos = ((eps,0,0), (0,eps,0), (0,0,eps))
        for i in range(3):
            perp1 = planet.normal(cept + dpos[i])
            dperp_dpos = (perp1 - perp) / eps

            ref = Vector3(perp.d_dpos.vals[...,i,:], perp.d_dpos.mask)
            self.assertTrue(abs(dperp_dpos - ref).max() < 1.e-4)

        # Test intercept_normal_to() derivative
        N = 1000
        pos = Vector3(np.random.random((N,3)) * 4.*REQ + REQ)
        pos.insert_deriv('pos', Vector3.IDENTITY, override=True)
        (cept,t) = planet.intercept_normal_to(pos, derivs=True, guess=True)
        self.assertTrue(abs(cept.element_mul(planet.unsquash).norm() -
                        planet.req).max() < 1.e-6)

        eps = 1.
        dpos = ((eps,0,0), (0,eps,0), (0,0,eps))
        perp = planet.normal(cept)
        for i in range(3):
            (cept1,t1) = planet.intercept_normal_to(pos + dpos[i], derivs=False,
                                                    guess=t)
            (cept2,t2) = planet.intercept_normal_to(pos - dpos[i], derivs=False,
                                                    guess=t)
            dcept_dpos = (cept1 - cept2) / (2*eps)
            self.assertTrue(abs(dcept_dpos.sep(perp) - Scalar.HALFPI).max() < 1.e-5)

            ref = Vector3(cept.d_dpos.vals[...,i], cept.d_dpos.mask)
            self.assertTrue(abs(dcept_dpos - ref).max() < 1.e-5)

            dt_dpos = (t1 - t2) / (2*eps)
            ref = t.d_dpos.vals[...,i]
            self.assertTrue(abs(dt_dpos/ref - 1).max() < 1.e-5)

        Path.reset_registry()
        Frame.reset_registry()

########################################
if __name__ == '__main__':
    unittest.main(verbosity=2)
################################################################################
