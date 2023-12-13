################################################################################
# oops/hosts/keck/nirc2.py: Keck subclass NIRC2
#
# This is an initial implementation of a Keck II FITS reader.  It does not
# support distortion models or instruments other than NIRC2.
################################################################################

try:
    import astropy.io.fits as pyfits
except ImportError:
    import pyfits
import oops
from . import Keck
import numpy as np

################################################################################
# Standard class methods
################################################################################

def from_file(filespec, **parameters):
    """A general, static method to return an Observation object based on a given
    data file generated by Keck/NIRC2.
    """

    # Open the file
    keck_file = pyfits.open(filespec)

    # Make an instance of the NIRC2 class
    this = NIRC2()

    # Confirm that the telescope is Keck
    if this.telescope_name(keck_file) != "Keck":
        raise IOError("not a Keck file: " + this.filespec(keck_file))

    # Confirm that the instrument is ACS
    if this.instrument_name(keck_file) != "NIRC2":
        raise IOError("not a Keck/NIRC2 file: " + this.filespec(keck_file))

    return NIRC2.from_opened_fitsfile(keck_file)

#===============================================================================
#===============================================================================
class NIRC2(Keck):
    """This class defines functions and properties unique to the NIRC2
    instrument. Everything else is inherited from higher levels in the class
    hierarchy.

    Objects of this class are empty; they only exist to support inheritance.
    """

    # Both NIRC2 detectors have a single filter wheel. The name is identified by
    # FITS parameter FILTER in the first header.
    def filter_name(self, keck_file):
        """The name of the filter for this particular NIRC2 detector."""

        return keck_file[0].header["FILTER"]

    #===========================================================================
    def define_fov(self, keck_file, **parameters):
        """An FOV object defining the field of view of the given image file."""

        camera = self.detector_name(keck_file)
        if camera == 'narrow':
            pix_scale = 0.009952 # arcsec/pixel
        elif camera == 'medium':
            pix_scale = 0.019829 # arcsec/pixel
        elif camera == 'wide':
            pix_scale = 0.039686 # arcsec/pixel

        pix_scale = pix_scale * oops.RPD/3600. # Convert to radians

        # Full field of view
        lines = 1024
        samples = 1024

        # Find the center RA,DEC of the image
        #
        # http://www2.keck.hawaii.edu/inst/KSDs/40/html/ksd40-55.f.html
        # INST X/Y -> RA,DEC:
        #   Flip Y?
        #   Rotate by INSTANGL                (=> Pointing origin offset)
        #   -ROTPPOSN - sign(FOCALSTN)*EL     (=> AZ,EL)
        #   (AZOFF, ELOFF)                    (=> AZ,RL OFFSET)
        #   AZ Flip
        #   +PARANG                           (=> RA,DEC)
        #   (RAOFF, DECOFF)                   (=> RA,DEC OFFSET)
        #
        # We reverse it:
        #   Start with RA,DEC OFFSET
        #   - (RAOFF, DECOFF)
        #   - PARANG
        #   AZ Flip
        #   - (AZOFF, ELOFF)
        #   +ROTPPOSN + sign(FOCALSTN)*EL
        #   Rotate by -INSTANGL
        #   Flip Y?
        #   => INST X/Y

#        ra_w_off = keck_file[0].header["RA"]
#        dec_w_off = keck_file[0].header["DEC"]
#        raoff = keck_file[0].header["RAOFF"]
#        decoff = keck_file[0].header["DECOFF"]
#        ra = ra_w_off - raoff
#        dec = dec_w_off - decoff
#
#        nparang = - keck_file[0].header["PARANG"] * oops.RPD
#        az_off = ra*np.cos(nparang) + dec*np.sin(nparang)
#        el_off = -ra*np.sin(nparang) + dec*np.cos(nparang)
#
#        # AZ flip?
#
#        azoff = 0. #keck_file[0].header["AZOFF"]
#        eloff = 0. #keck_file[0].header["ELOFF"]

        uscale = pix_scale
        vscale = pix_scale

        if keck_file[0].header['INSTFLIP'] != 'yes':  # Flip Y
            vscale = -vscale

        # Display directions: [u,v] = [right,down]
        full_fov = oops.fov.FlatFOV((uscale,vscale), (samples,lines))

        return full_fov

    #===========================================================================
    @staticmethod
    def from_opened_fitsfile(keck_file, **parameters):
        """A general class method to return an Observation object based on an
        Keck data file generated by Keck/NIRC2.
        """

        # Make an instance of the NIRC2 class
        this = NIRC2()

        # Figure out the detector
        detector = this.detector_name(keck_file)

        if detector != "narrow" and detector != 'medium' and detector != 'wide':
            raise IOError("unsupported camera in Keck/NIRC2 file " +
                          this.filespec(keck_file) + ": " + detector)

        obs = this.construct_snapshot(keck_file, **parameters)

        return obs

################################################################################
