################################################################################
# oops/inst/hst/wfc3/__init__.py: HST subclass WFC3
################################################################################

try:
    import astropy.io.fits as pyfits
except ImportError:
    import pyfits
import oops
from oops.inst.hst import HST

################################################################################
# Standard class methods
################################################################################

#===============================================================================
# from_file
#===============================================================================
def from_file(filespec, **parameters):
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    ""
    A general, static method to return an Observation object based on a given
    data file generated by HST/WFC3.
    """
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

    #--------------------
    # Open the file	     
    #--------------------
    hst_file = pyfits.open(filespec)

    #----------------------------------------
    # Make an instance of the WFC3 class     	 
    #----------------------------------------
    this = WFC3()

    #--------------------------------------
    # Confirm that the telescope is HST        
    #--------------------------------------
    if this.telescope_name(hst_file) != "HST":
        raise IOError("not an HST file: " + this.filespec(hst_file))

    #---------------------------------------
    # Confirm that the instrument is ACS    	
    #---------------------------------------
    if this.instrument_name(hst_file) != "WFC3":
        raise IOError("not an HST/WFC3 file: " + this.filespec(hst_file))

    return WFC3.from_opened_fitsfile(hst_file)
#===============================================================================




#*******************************************************************************
# WFC3
#*******************************************************************************
class WFC3(HST):
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    """
    This class defines functions and properties unique to the WFC3
    instrument. Everything else is inherited from higher levels in the class
    hierarchy.

    Objects of this class are empty; they only exist to support inheritance.
    """
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++


    #===========================================================================
    # filter_name
    #  Both WFC3 detectors have a single filter wheel. The name is identified by
    #  FITS parameter FILTER in the first header.
    #===========================================================================
    def filter_name(self, hst_file):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Returns the name of the filter for this particular NICMOS detector.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        return hst_file[0].header["FILTER"]
    #===========================================================================



    #===========================================================================
    # from_opened_fitsfile
    #===========================================================================
    @staticmethod
    def from_opened_fitsfile(hst_file, **parameters):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        A general class method to return an Observation object based on an
        HST data file generated by HST/WFC3.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

        #----------------------------------------
        # Make an instance of the WFC3 class	 	 
        #----------------------------------------
        this = WFC3()

        #------------------------------
        # Figure out the detector              
        #------------------------------
        detector = this.detector_name(hst_file)

        if detector == "UVIS":
            from oops.inst.hst.wfc3.uvis import UVIS
            obs = UVIS.from_opened_fitsfile(hst_file, **parameters)

        elif detector == "IR":
            from oops.inst.hst.wfc3.ir import IR
            obs = IR.from_opened_fitsfile(hst_file, **parameters)

        else:
            raise IOError("unsupported detector in HST/WFC3 file " +
                          this.filespec(hst_file) + ": " + detector)

        return obs
     #===========================================================================


 #*******************************************************************************


################################################################################
