################################################################################
# oops/backplanes/pixel.py: pixel coordinate backplanes
################################################################################

import oops

from oops.constants import C
from oops.backplane import Backplane

#===============================================================================
def radius_in_pixels(self, event_key):
    """Gridless approximate apparent radius of the body in pixels.

    Input:
        event_key       key defining the event on the body's path.
    """
    gridless_key = Backplane.gridless_event_key(event_key)
    key = ('radius_in_pixels', gridless_key)
    if key in self.backplanes:
        return self.get_backplane(key)

    # compute apparent distance
    event = self.get_surface_event(gridless_key, arrivals=True)
    distance = event._dep_lt_*C

    # compute apparent enclosing radius
    (body, mod) = Backplane.get_body_and_modifier(gridless_key[1])
    if mod == 'RING':
        body = body.ring_system_body
    radius = body.radius/distance / self.obs.fov.uv_scale.values[0]

    return self.register_backplane(key, radius)

#===============================================================================
def _center_coordinates(self, gridless_key):
    """Internal function to compute (u,v) coordinates of the center of the disk.

    Input:
        event_key       key defining the event on the body's path.
        gridless_key    gridless event key
    """
    
    body = oops.Body.lookup(gridless_key[1])
    return self.obs.uv_from_path(body.path)

#===============================================================================
def center_coordinate(self, event_key, direction="x"):
    """Gridless v coordinate of the center of the disk.

    Input:
        event_key       key defining the event on the body's path.
        direction       "x" or "y".
    """
    gridless_key = Backplane.gridless_event_key(event_key)
    key = ('center_coordinate', gridless_key) + (direction,)
    if key in self.backplanes:
        return self.get_backplane(key)

    uv = self._center_coordinates(gridless_key)
    index = 0 if direction == "x" else 1
    return self.register_backplane(key, uv.to_scalars()[index])

################################################################################

# Add these functions to the Backplane module
Backplane._define_backplane_names(globals().copy())

################################################################################