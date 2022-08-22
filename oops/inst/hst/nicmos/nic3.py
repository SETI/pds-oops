################################################################################
# oops/inst/hst/nicmos/nic3.py: HST/NICMOS subclass NIC3
################################################################################

try:
    import astropy.io.fits as pyfits
except ImportError:
    import pyfits
from oops.inst.hst.nicmos import NICMOS

################################################################################
# Standard class methods
################################################################################

#===============================================================================
# from_file
#===============================================================================
def from_file(filespec, **parameters):
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    """
    A general, static method to return an Observation object based on a given
    data file generated by HST/NICMOS/NIC1.
    """
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

    #---------------------
    # Open the file
    #---------------------
    hst_file = pyfits.open(filespec)

    #---------------------------------------
    # Make an instance of the NIC3 class
    #---------------------------------------
    this = NIC3()

    #----------------------------------------
    # Confirm that the telescope is HST
    #----------------------------------------
    if this.telescope_name(hst_file) != "HST":
        raise IOError("not an HST file: " + this.filespec(hst_file))

    #-------------------------------------------
    # Confirm that the instrument is NICMOS
    #-------------------------------------------
    if this.instrument_name(hst_file) != "NICMOS":
        raise IOError("not an HST/NICMOS file: " + this.filespec(hst_file))

    #----------------------------------------
    # Confirm that the detector is NIC2
    #----------------------------------------
    if this.detector_name(hst_file) != "NIC3":
        raise IOError("not an HST/NICMOS/NIC3 file: " + this.filespec(hst_file))

    return NIC3.from_opened_fitsfile(hst_file, **parameters)
#===============================================================================



#*******************************************************************************
# NIC3
#*******************************************************************************
class NIC3(NICMOS):
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    """
    This class defines functions and properties unique to the NIC3 detector.
    Everything else is inherited from higher levels in the class hierarchy.

    Objects of this class are empty; they only exist to support inheritance.
    """
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

    #-----------------------------------------------------
    # Used by select_syn_files, defined in NICMOS.py
    #-----------------------------------------------------
    DETECTOR_SYN_FILES = ["NICMOS/nic3_bend_???_syn.fits",
                          "NICMOS/nic3_cmask_???_syn.fits",
                          "NICMOS/nic3_dewar_???_syn.fits",
                          "NICMOS/nic3_image_???_syn.fits",
                          "NICMOS/nic3_para1_???_syn.fits",
                          "NICMOS/nic3_para2_???_syn.fits"]

    FILTER_SYN_FILE_PARTS = ["NICMOS/nic3_", "_???_syn.fits"]

    #===========================================================================
    # from_opened_fitsfile
    #===========================================================================
    @staticmethod
    def from_opened_fitsfile(hst_file, **parameters):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        A general class method to return an Observation object based on an
        HST data file generated by HST/NICMOS/NIC1.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        return NIC3().construct_snapshot(hst_file, **parameters)
    #===========================================================================

#*******************************************************************************


################################################################################
