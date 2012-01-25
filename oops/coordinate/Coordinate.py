################################################################################
# class Coordinate
#
# 1/24/12 (MRS) Added.
################################################################################

import numpy as np

import oops

class Coordinate(object):
    """A Coordinate is a generic class used to describe the default numeric
    range, units, and formating of a geometric quantity.
    """

    def __init__(self, unit, format,
                       minimum=-np.inf, maximum=np.inf, modulus=None,
                       reference=0., negated=False):
        """The general constructor for a Coordinate object.

        Input:
            unit        the default Unit object used by the coordinate.
            format      the default Format object used by the coordinate.
            minimum     the global minimum value of a coordinate, if any,
                        specified in the default units for the coordinate.
            maximum     the global maximum value of a coordinate, if any.
            modulus     the modulus value of the coordinate, if any, specified
                        in the default units for the coordinate. If not None,
                        then all coordinate values returned will fall in the
                        range (minimum, minimum+modulus).
            reference   the default reference coordinate relative to which
                        values are specified, in default units. If defined,
                        then this is this location relative to the origin of the
                        standard coordinate system corresponding to a value of
                        zero for this coordinate value.
            negated     if True, then these coordinate values increase from the
                        reference point in a direction opposite to the standard
                        coordinates.

        Note: Currently the maximum value is unused, and the minimum is only
        used when a modulus is also given. We might eventually use minimum and
        maximum to implement range checks.
        """

        self.unit      = unit
        self.format    = format
        self.minimum   = minimum
        self.maximum   = maximum
        self.modulus   = modulus
        self.reference = reference
        self.negated   = negated

    def to_standard(self, value):
        """Converts the value of a coordinate to standard units involving km,
        seconds and radians, and measured in the default direction relative to
        the default origin."""

        if self.negated: value = -value
        value += self.reference
        return self.unit.to_standard(value, unit)

    def to_coord(self, value, units):
        """Converts the value of a coordinate from standard units involving km,
        seconds and radians into a value relative to the specified units, origin
        and direction. Applies the modulus if any. If units is True, then a
        UnitScalar object is returned; otherwise, a Scalar object is returned.
        """

        value = self.unit.to_unit(value)
        value -= self.reference

        if self.negated: value = -value

        if self.modulus is not None:
            value = self.minimum + (value - self.minimum) % self.modulus

        if units:
            return oops.UnitScalar(value, self.unit)
        else:
            return Scalar.as_scalar(value)

################################################################################