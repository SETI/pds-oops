################################################################################
# oops/surface_/unittester.py
################################################################################

import unittest

from oops.surface_.ansa        import Test_Ansa
from oops.surface_.ellipsoid   import Test_Ellipsoid
from oops.surface_.limb        import Test_Limb
from oops.surface_.nullsurface import Test_NullSurface
from oops.surface_.orbitplane  import Test_OrbitPlane
from oops.surface_.ringplane   import Test_RingPlane
from oops.surface_.spheroid    import Test_Spheroid
from oops.surface_.spicebody   import Test_spice_body
from oops.surface_.surface     import Test_Surface

########################################
if __name__ == '__main__':
    unittest.main(verbosity=2)
################################################################################