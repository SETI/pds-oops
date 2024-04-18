################################################################################
# oops/hosts/hst/acs/sbc.py: HST/ACS subclass SBC
################################################################################

try:
    import astropy.io.fits as pyfits
except ImportError:
    import pyfits
from . import ACS

################################################################################
# Standard class methods
################################################################################

def from_file(filespec, **parameters):
    """A general, static method to return an Observation object based on a given
    data file generated by HST/ACS/SBC.
    """

    # Open the file
    hst_file = pyfits.open(filespec)

    # Make an instance of the SBC class
    this = SBC()

    # Confirm that the telescope is HST
    if this.telescope_name(hst_file) != "HST":
        raise IOError("not an HST file: " + this.filespec(hst_file))

    # Confirm that the instrument is ACS
    if this.instrument_name(hst_file) != "ACS":
        raise IOError("not an HST/ACS file: " + this.filespec(hst_file))

    # Confirm that the detector is SBC
    if this.detector_name(hst_file) != "SBC":
        raise IOError("not an HST/ACS/SBC file: " + this.filespec(hst_file))

    return SBC.from_opened_fitsfile(hst_file, **parameters)

IDC_DICT = None

GENERAL_SYN_FILES = ["OTA/hst_ota_???_syn.fits",
                     "ACS/acs_sbc_mama_???_syn.fits"]

FILTER_SYN_FILE = ["ACS/acs_", "_???_syn.fits"]

#===============================================================================
#===============================================================================
class SBC(ACS):
    """This class defines functions and properties unique to the NIC1 detector.
    Everything else is inherited from higher levels in the class hierarchy.

    Objects of this class are empty; they only exist to support inheritance.
    """

    def define_fov(self, hst_file, **parameters):
        """An FOV object defining the field of view of the given image file."""

        global IDC_DICT

        # Load the dictionary of IDC parameters if necessary
        if IDC_DICT is None:
            IDC_DICT = self.load_idc_dict(hst_file, ("FILTER1",))

        # Define the key into the dictionary
        idc_key = (hst_file[0].header["FILTER1"],)

        # Use the default function defined at the HST level for completing the
        # definition of the FOV
        return self.construct_fov(IDC_DICT[idc_key], hst_file)

    #===========================================================================
    def filter_name(self, hst_file, layer=None):
        """The name of the filter for this particular ACS detector."""

        return hst_file[0].header["FILTER1"]

    #===========================================================================
    def select_syn_files(self, hst_file, **parameters):
        """The list of SYN files containing profiles that are to be multiplied
        together to obtain the throughput of the given instrument, detector, and
        filter combination.
        """

        # Copy all the standard file names
        syn_filenames = []
        for filename in GENERAL_SYN_FILES:
            syn_filenames.append(filename)

        # Add the filter file name
        syn_filenames.append(FILTER_SYN_FILE[0] +
                             hst_file[0].header["FILTER1"].lower() +
                             FILTER_SYN_FILE[1])

        return syn_filenames

    #===========================================================================
    @staticmethod
    def from_opened_fitsfile(hst_file, **parameters):
        """A general class method to return an Observation object based on an
        HST data file generated by HST/ACS/SBC.
        """

        return SBC().construct_snapshot(hst_file, **parameters)

################################################################################
