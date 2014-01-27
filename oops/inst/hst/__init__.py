################################################################################
# oops/inst/hst/__init__.py
#
# 4/8/12 MRS - corrected a small rotational error in the frame, due to the
#   peculiar way that the HST distortion models interact with the definition of
#   the ORIENT parameter. See the parameter v_wrt_y_deg.
#
# 6/7/12 MRS - removed error condition that arises for ramp filters; instead,
#   calibration objects will be None. Replaced the Cmatrix frame by a Tracker
#   frame to track moving targets properly. Modified register_frame() to work
#   with NICMOS and support WFPC2.
#
# 10/28/12 MRS - fixed POS TARG values to account for improperly defined y-axis
#   when an aperture was in use.
################################################################################

import numpy as np
import os
import re
import pyfits
import glob
import unittest
import warnings

import julian
import solar
import tabulation as tab
import oops

########################################
# Global Variables
########################################

# A handy constant
RADIANS_PER_ARCSEC = np.pi / 180. / 3600.

# After a call to set_idc_path(), these global variables will be defined:

HST_IDC_PATH = None
    # The directory prefix pointing to the location where all HST IDC files
    # reside. IDC files contain the distortion model of each HST field of view.

IDC_FILE_NAME_DICT = None
    # A dictionary that associates each instrument and detector with the name of
    # a particular IDC file.

# After a call to set_syn_path(), this global variable will be defined:

HST_SYN_PATH = None
    # The directory prefix pointing to the location where all HST SYN files
    # reside. SYN files tabulate the filter throughput as a function of
    # wavelength in Angstroms. This directory has subdirectories named ACS,
    # WFC3, WFPC2, NICMOS, etc.

# This should be a reasonably complete procedure for mapping the first three
# letters of the P.I.'s target name to the SPICE name of the target body.

HST_TARGET_DICT = {"MAR": "MARS",
                   "JUP": "JUPITER",
                   "SAT": "SATURN",
                   "URA": "URANUS",
                   "NEP": "NEPTUNE",
                   "PLU": "PLUTO",
                   "IO" : "IO",
                   "EUR": "EUROPA",
                   "GAN": "GANYMEDE",
                   "CAL": "CALLISTO",
                   "ENC": "ENCELADUS",
                   "TIT": "TITAN",
                   "PHO": "PHOEBE"}

# Define some important paths and frames
oops.define_solar_system("1990-01-01", "2020-01-01")

################################################################################
# Standard instrument methods
################################################################################

def from_file(filespec, **parameters):
    """A general, static method to return an Observation object based on a given
    data file generated by the Hubble Space Telescope.

    If parameters["data"] is False, no data or associated arrays are loaded.
    If parameters["calibration"] is False, no calibration objects are created.
    If parameters["headers"] is False, no header dictionary is returned.

    If parameters["astrometry"] is True, this is equivalent to data=False,
    calibration=False, headers=False.

    If parameters["reference"] is specified, then the frame of the returned
    observation will employ the same frame as that of the reference observation.
    """

    hst_file = pyfits.open(filespec)
    return HST.from_opened_fitsfile(hst_file, **parameters)

################################################################################
# Class HST
################################################################################

class HST(object):
    """This class defines functions and properties unique to the Hubble Space
    Telescope.

    Objects of this class are empty; they only exist to support inheritance.
    """

    def filespec(self, hst_file):
        """Returns the full directory path and name of the file."""

        # Found by poking around inside a pyfits object
        return hst_file._HDUList__file._File__file.name

    def telescope_name(self, hst_file):
        """Returns the name of the telescope from which the observation was
        obtained."""

        return hst_file[0].header["TELESCOP"]

    def instrument_name(self, hst_file):
        """Returns the name of the HST instrument associated with the file."""

        return hst_file[0].header["INSTRUME"]

    # The default FITS keyword defining the HST instrument's detector is
    # "DETECTOR". However, this must be overridden by some instruments.
    def detector_name(self, hst_file, **parameters):
        """Returns the name of the detector on the HST instrument that was used
        to obtain this file."""

        return hst_file[0].header["DETECTOR"]

    def data_array(self, hst_file, **parameters):
        """Returns an array containing the data."""

        return hst_file[1].data

    def error_array(self, hst_file, **parameters):
        """Returns an array containing the uncertainty values associated with
        the data."""

        return hst_file[2].data

    def quality_mask(self, hst_file, **parameters):
        """Returns an array containing the data quality mask."""

        return hst_file[3].data

    # This works for Snapshot observations. Others must override.
    def time_limits(self, hst_file, **parameters):
        """Returns a tuple containing the overall start and end times of the
        observation."""

        date_obs = hst_file[0].header["DATE-OBS"]
        time_obs = hst_file[0].header["TIME-OBS"]
        exptime  = hst_file[0].header["EXPTIME"]

        tdb0 = julian.tdb_from_tai(julian.tai_from_iso(date_obs + "T" +
                                                       time_obs))
        tdb1 = tdb0 + exptime

        return (tdb0, tdb1)

    def pos_targ(self, hst_file, **parameters):
        """Returns a tuple containing the POS TARG values (x,y) used for this
        observation, and as specified in the observation's coordinate frame. It
        returns None if the POS TARG values are not found in the file and are
        not specified in the parameter dictionary via an argument "pos_targ".
        """

        if "pos_targ" in parameters.keys():
            return parameters["pos_targ"]

        if "POSTARG1" in hst_file[0].header.keys():
            return (hst_file[0].header["POSTARG1"],
                    hst_file[0].header["POSTARG2"])

        return None

    def register_frame(self, hst_file, fov, index=1, suffix="", **parameters):
        """Returns the ID of a frame that rotates from J2000 coordinates into
        the (u,v) coordinates of the HST observation.

        Normally, this is a Tracker frame constructed for this particular
        observation. However, if parameters["reference"] is specified as another
        HST observation, then...

        * if POS TARG is the same, the same frame ID is returned;

        * otherwise, a new PosTarg frame is defined as an offset from the frame
          of the reference observation, and the ID of this new frame is
          returned.

        The index and suffix arguments are used by WFPC2 to override the default
        behavior.
        """

        if "reference" in parameters.keys():
            return self.register_postarg_frame(hst_file, fov, index, suffix,
                                                              **parameters)

        else:
            return self.register_tracker_frame(hst_file, fov, index, suffix,
                                                              **parameters)

    def register_tracker_frame(self, hst_file, fov, index=1, suffix="",
                                                    **parameters):
        """Constructs and returns a Tracker frame for the observation. This
        frame ensures that the target object stays at the same location on the
        CCD for the duration of the observation.
        """

        header1 = hst_file[index].header

        if header1["CTYPE1"][:2] != "RA" or header1["CTYPE2"][:3] != "DEC":
            return None

        ra  = header1["CRVAL1"]     # applies at the observation start time
        dec = header1["CRVAL2"]

        # v_wrt_y_deg is the angle from the y-axis of the camera frame to the
        # v-axis of the pixel grid, in degrees. I find this to be nonzero in HST
        # distortion models. Because the camera ORIENT is defined relative to
        # the v-axis, we need to subtract this value to get the orientation of
        # the y-axis. MRS 4/8/12.

        uv_center = fov.uv_from_xy((0,0))
        xy_center = fov.xy_from_uv(uv_center, derivs=True)

        v_wrt_y_deg = np.arctan(xy_center.d_duv.vals[0,1] /
                                xy_center.d_duv.vals[1,1]) * oops.DPR

        # Get ORIENT
        try:
            orient = header1["ORIENTAT"]
        except KeyError:
            # If ORIENT is missing, as is the case for NICMOS, we can construct
            # it from the partial derivatives CD1_1 = dRA/du, CD1_2 = dRA/dv,
            # CD2_1 = dDEC/du, CD2_2 = dDEC/dv

            dnorth_dv = header1["CD2_2"]
            dleft_dv  = header1["CD1_2"]
            # Note: Previously I had this:
            #   dleft_dv  = header1["CD1_2"] * np.cos(ra * oops.RPD)
            # However, I found that the cosine term is not used by STScI.

            orient = np.arctan2(dleft_dv, dnorth_dv) * oops.DPR

        clock = orient - v_wrt_y_deg

        frame_id = hst_file[0].header["FILENAME"] + suffix

        # Applies at the start time of the observation
        cmatrix = oops.frame.Cmatrix.from_ra_dec(ra, dec, clock,
                                                 frame_id + "_CMATRIX")

        # Applies for the duration of the observation
        time_limits = self.time_limits(hst_file)
        tracker = oops.frame.Tracker(cmatrix,
                                     self.target_body(hst_file).path_id,
                                     "EARTH", time_limits[0], frame_id)

        return frame_id

    def register_postarg_frame(self, hst_file, fov, index=1, suffix="",
                                                    **parameters):
        """If necessary, constructs a PosTarg frame for the observation and
        returns its ID. Otherwise, it returns the ID of the frame used by the
        reference observation."""

        reference = parameters["reference"]

        assert self.instrument_name(hst_file) == reference.instrument
        assert self.detector_name(hst_file) == reference.detector

        new_pos_targ = self.pos_targ(hst_file, **parameters)
        assert new_pos_targ is not None

        if reference.pos_targ == new_pos_targ:
            return reference.frame_id

        xpos =  RADIANS_PER_ARCSEC * (new_pos_targ[0] - reference.pos_targ[0])
        ypos = -RADIANS_PER_ARCSEC * (new_pos_targ[1] - reference.pos_targ[1])

        # Don't forget to rotate POS TARG values to the proper y-axis!
        # The values of POS TARG are defined relative to the y-axis of the
        # aperture (aka "v"), not the y-axis of the frame.
        uv_center = fov.uv_from_xy((0,0))
        xy_center = fov.xy_from_uv(uv_center, derivs=True)

        v_wrt_y = np.arctan(xy_center.d_duv.vals[0,1] /
                            xy_center.d_duv.vals[1,1])

        cos_angle = np.cos(v_wrt_y)
        sin_angle = np.sin(v_wrt_y)

        xpos_corrected =  xpos * cos_angle + ypos * sin_angle
        ypos_corrected = -xpos * sin_angle + ypos * cos_angle

        frame_id = hst_file[0].header["FILENAME"]
        frame = oops.frame.PosTarg(xpos_corrected, ypos_corrected,
                                   reference.frame_id, frame_id)

        return frame_id

    def dn_per_sec_factor(self, hst_file):
        """Returns a factor that converts a pixel value in DN per second.
        For instruments like WFC3/UVIS this is just 1/exposure time.
        For instruments like WFC3/IR this is 1.0, since the pixel values are
        already in DN per second.
        This method is overridden by the various subclasses.
        
        Input:
            hst_file        the object returned by pyfits.open()
            
        Return              the factor to multiply a pixel value by to get DN/sec
        """
        assert False  # Must be overridden

    def iof_calibration(self, hst_file, fov, extended=True, **parameters):
        """Returns a Calibration object suitable for integrating the I/F of
        point objects in an HST image.

        Input:
            hst_file        the object returned by pyfits.open().
            fov             the field of view describing the observation.
            extended        True to provide a calibration for extended sources,
                            in which case field-of-view distortion is ignored;
                            False to provide a calibration object for point
                            sources, in which case the distortion of the field
                            of view must be taken into account.
            parameters      a dictionary of arbitrary parameters.
                parameters["solar_range"]
                            if present, this parameters defines the Sun-target
                            distance in AU. If not defined or None, the range
                            is inferred from the observation's target name and
                            mid-time and the mid-time of the exposure, using 
                            the loaded SPICE kernels.
                parameters["solar_model"]
                            if present, this is the name of the model to use for
                            the solar flux density, either "STIS" or "COLINA".
                            If not defined or None, the "STIS" model is used.

        Return              a Calibration object that converts from DN to
                            reflectivity.
        """

        # Look up the solar range...
        try:
            solar_range = parameters["solar_range"]
        except KeyError:
            solar_range = None

        # If necessary, get the solar range from the target name
        if solar_range is None:
            target_body = self.target_body(hst_file)
            target_sun_path = oops.registry.connect_paths(target_body.path_id,
                                                          "SUN")
            # Paths of the relevant bodies need to be defined in advance!

            times = self.time_limits(hst_file)
            tdb = (times[0] + times[1]) / 2.
            sun_event = target_sun_path.event_at_time(tdb)
            solar_range = sun_event.pos.norm().vals / solar.AU

        # Look up the solar model...
        try:
            solar_model = parameters["solar_model"]
        except KeyError:
            solar_model = None

        if solar_model is None:
            solar_model = "STIS"

        # Generate the calibration factor
        try:
            try:
                photflam = hst_file[1].header["PHOTFLAM"]
            except:
                photflam = hst_file[0].header["PHOTFLAM"]
        except KeyError:
            raise IOError("PHOTFLAM calibration factor not found in file " +
                          self.filespec(hst_file))

        texp_factor = self.dn_per_sec_factor(hst_file) 
        factor = photflam * texp_factor / fov.uv_area / self.solar_f(hst_file, solar_range, solar_model)

        # Create and return the calibration for solar reflectivity
        if extended:
            return oops.calib.ExtendedSource("I/F", factor)
        else:
            return oops.calib.PointSource("I/F", factor, fov)

    def target_body(self, hst_file):
        """This procedure returns the body object defining the image target. It
        is based on educated guesses from the target name used by the P.I."""

        global HST_TARGET_DICT

        targname = hst_file[0].header["TARGNAME"]

        if len(targname) >= 2:      # Needed to deal with 2-letter "IO"
            key2 = targname[0:2]
            key3 = key2
        if len(targname) >= 3:
            key3 = targname[0:3]

        try:
            body_name = HST_TARGET_DICT[key3]
        except KeyError:
            body_name = HST_TARGET_DICT[key2]
        # Raises a KeyError on failure

        return oops.registry.body_lookup(body_name)

    def construct_snapshot(self, hst_file, **parameters):
        """Returns a Snapshot object for the data found in the specified image.
        """

        fov = self.define_fov(hst_file, **parameters)

        times = self.time_limits(hst_file, **parameters)

        snapshot = oops.obs.Snapshot(
                        axes = ("v","u"),
                        tstart = times[0],
                        texp = times[1] - times[0],
                        fov = fov,
                        path_id = "EARTH",
                        frame_id = self.register_frame(hst_file, fov,
                                                       **parameters),
                        target = self.target_body(hst_file),
                        telescope = self.telescope_name(hst_file),
                        instrument = self.instrument_name(hst_file),
                        detector = self.detector_name(hst_file),
                        filter = self.filter_name(hst_file),
                        pos_targ = self.pos_targ(hst_file, **parameters))

        # Interpret loader options
        if "astrometry" in parameters.keys() and parameters["astrometry"]:
            include_data = False
            include_calibration = False
            include_headers = False

        else:
            include_data = ("data" not in parameters.keys() or
                            parameters["data"])
            include_calibration = ("calibration" not in parameters.keys() or
                            parameters["calibration"])
            include_headers = ("headers" not in parameters.keys() or
                            parameters["headers"])

        if include_data:
            data = self.data_array(hst_file, **parameters)
            error = self.error_array(hst_file, **parameters)
            quality = self.quality_mask(hst_file, **parameters)

            snapshot.insert_subfield("data", data)
            snapshot.insert_subfield("error", error)
            snapshot.insert_subfield("quality", quality)

        if include_calibration:
            try:
                point_calib = self.iof_calibration(hst_file, fov, False,
                                                   **parameters)
                extended_calib = self.iof_calibration(hst_file, fov, True,
                                                      **parameters)
            except IOError, AttributeError:
                point_calib = None
                extended_calib = None

            snapshot.insert_subfield("point_calib", point_calib)
            snapshot.insert_subfield("extended_calib", extended_calib)

        if include_headers:
            headers = []
            for objects in hst_file:
                headers.append(objects.header)

            snapshot.insert_subfield("headers", headers)

        return snapshot

    ############################################################################
    # IDC (distortion model) support functions
    ############################################################################

    def set_idc_path(self, idc_path):
        """Defines the directory path to the IDC files. It must be called before
        any HST files are loaded. The alternative is to define the environment
        variable HST_IDC_PATH."""

        global HST_IDC_PATH
        global IDC_FILE_NAME_DICT

        # Save the argument as a global variable. Make sure it ends with slash.
        HST_IDC_PATH = idc_path

        # We associate files with specific instruments and detector combinations
        # via a dictionary. The definition of this dictionary resides in the
        # same directory as the IDC files themselves, in a file called
        #   IDC_FILE_NAME_DICT.txt
        # Every time we update an IDC file, we will need to update this file
        # too.
        #
        # The file has this syntax:
        #   ("ACS",   "HRC"): "p7d1548qj_idc.fits"
        #   ("WFPC2", ""   ): "v5r1512gi_idc.fits"
        # etc., where each row defines a dictionary entry comprising a key
        # (instrument name, detector name) and the name of the associated
        # IDC file in FITS format.

        # Compile a regular expression that ensures nothing bad is contained in
        # this file.
        regex = re.compile(r' *\( *("\w*" *, *)*"\w*" *\) *: *"\w+\.fits" *$',
                           re.IGNORECASE)

        # Read the key:value pairs and make sure they are clean
        f = open(HST_IDC_PATH + "IDC_FILE_NAME_DICT.txt")
        lines = []
        for line in f:
            if regex.match(line) is False:
                raise IOError("syntax error in IDC definition: " + line)

            lines.append(line)
        f.close()

        # Define the global dictionary
        IDC_FILE_NAME_DICT = eval("{" + ", ".join(lines) + "}")

        return

    def idc_filespec(self, hst_file):
        """Returns the full directory path and file name of an IDC file, given
        the associated FITS file object.
        """

        # Define the directory path and load the dictionary if necessary
        if HST_IDC_PATH is None:
            self.set_idc_path(os.environ["HST_IDC_PATH"])

        # Look up and return the filespec
        detector_key = (self.instrument_name(hst_file),
                        self.detector_name(hst_file))

        return os.path.join(HST_IDC_PATH, IDC_FILE_NAME_DICT[detector_key])

    def load_idc_dict(self, hst_file, keys):
        """Returns the IDC dictionary containing all the parameters in an IDC
        file.

        Input:
            hst_file        the information returned by pyfits.open().

            keys            a tuple containing the names of the columns to use
                            as the keys of the returned dictionary. For example,
                            if keys = ("FILTER1","FILTER2"), then the pair of
                            filter names will be the key into the dictionary.

        Return:             A dictionary in which each entry is itself a
                            dictionary containing the parameter/value pairs from
                            a single row of the IDC file. The rows are keyed by
                            a tuple of the values in the columns specified by
                            the keys.
        """

        # Open the IDC FITS file
        idc_filespec = self.idc_filespec(hst_file)
        idc_file = pyfits.open(idc_filespec)
        object1 = idc_file[1]
        header1 = object1.header

        # Get the names of columns
        ncolumns = header1["TFIELDS"]
        names = []
        for c in range(ncolumns):
            key = "TTYPE" + str(c+1)
            names.append(header1[key])

        # Initiailize the dictionary to be returned
        idc_dict = {}

        # For each row of the IDC table...
        nrows = header1["NAXIS2"]
        for r in range(nrows):

            # if the direction is not FORWARD, skip this row
            if object1.data[r]["DIRECTION"] != "FORWARD": continue

            # Initialize the row's dictionary
            row_dict = {}

            # For each column...
            for c in range(ncolumns):

                # Convert the value to a standard Python type
                value = object1.data[r][c]
                dtype = str(object1.data.dtype[c])

                if   "S" in dtype: value = str(value)
                elif "i" in dtype: value = int(value)
                elif "f" in dtype: value = float(value)
                else:
                    raise ValueError("Unrecognized dtype: " + dtype)

                # Add to the row's dictionary
                row_dict[names[c]] = value

            # Derive the key for this row
            tuple = ()
            for key in keys:
                value = row_dict[key]
                if type(value) == type(""): value = value.strip()

                tuple += (value,)

            # Add a new entry to the dictionary
            idc_dict[tuple] = row_dict

        return idc_dict

    def construct_idc_fov(self, fov_dict):
        """Returns the FOV object associated with the full field of view of an
        HST instrument, based on a dictionary of associated IDC parameter
        values.

        Input:
            fov_dict    a dictionary defining the associated IDC parameters.
                        This is one of the entries in the dictionary returned by
                        load_idc_file().

        Return:         a Polynomial FOV object.
        """

        # Determine the order of the transform
        if "CX11" in fov_dict: order = 1
        if "CX22" in fov_dict: order = 2
        if "CX33" in fov_dict: order = 3
        if "CX44" in fov_dict: order = 4
        if "CX55" in fov_dict: order = 5
        if "CX66" in fov_dict: order = 6

        # Create an empty array for the coefficients
        cxy = np.zeros((order+1, order+1, 2))

        # The first index is the order of the term.
        # The second index is the coefficient on the sample axis.
        for   i in range(1, order+1):
          for j in range(i+1):
            try:
                # In these arrays, the indices are the powers of x (increasing
                # rightward) and y (increasing upward).
                cxy[j,i-j,0] =  fov_dict["CX" + str(i) + str(j)]
                cxy[j,i-j,1] = -fov_dict["CY" + str(i) + str(j)]
            except KeyError: pass

        return oops.fov.Polynomial(cxy * RADIANS_PER_ARCSEC,
                        (fov_dict["XSIZE"], fov_dict["YSIZE"]),
                        (fov_dict["XREF" ], fov_dict["YREF" ]),
                        (fov_dict["SCALE"] * RADIANS_PER_ARCSEC)**2)

    def construct_drz_fov(self, fov_dict, hst_file):
        """Returns the FOV object associated with the full field of view of a
        "drizzled" (geometrically reprojected) image.

        Input:
            fov_dict    a dictionary defining the associated IDC parameters.
                        This is one of the entries in the dictionary returned by
                        load_idc_file().
            hst_file    the FITS file object returned by pyfits.open().

        Return:         a Flat FOV object.
        """

        # Define the field of view without sub-sampling
        # *** SHOULD BE CHECKED ***
        scale = fov_dict["SCALE"] * RADIANS_PER_ARCSEC
        scale = oops.Pair((scale, -scale))

        # Extract all size and offset parameters from the header
        header1 = hst_file[1].header
        crpix   = oops.Pair((header1["CRPIX1"],   header1["CRPIX2"]  ))
        sizaxis = oops.Pair((header1["SIZAXIS1"], header1["SIZAXIS2"]))
        binaxis = oops.Pair((header1["BINAXIS1"], header1["BINAXIS2"]))

        return oops.fov.Flat(scale * binaxis, sizaxis, crpix)

    def construct_fov(self, fov_dict, hst_file):
        """Returns the FOV object associated with an HST instrument, allowing for
        drizzling, for subarrays, overscan pixels and pixel binning.

        Input:
            fov_dict    a dictionary defining the associated IDC parameters.
                        This is one of the entries in the dictionary returned by
                        load_idc_file().
            hst_file    the FITS file object returned by pyfits.open().
        """

        # Check for a drizzle correction
        # try:
        #     drizcorr = hst_file[0].header["DRIZCORR"]
        # except KeyError:
        #     drizcorr = ""

        # If drizzled, construct and return a Flat FOV
        # if drizcorr == "COMPLETE":

        suffix = self.filespec(hst_file)[-8:-5].upper()
        if suffix == "DRZ":
            return self.construct_drz_fov(fov_dict, hst_file)

        # Otherwise, construct the default Polynomial FOV
        fov = self.construct_idc_fov(fov_dict)

        # Extract all size and offset parameters from the header
        header1 = hst_file[1].header
        crpix   = oops.Pair((header1["CRPIX1"], header1["CRPIX2"]))
        naxis   = oops.Pair((header1["NAXIS1"], header1["NAXIS2"]))

        try:
            centera = oops.Pair((header1["CENTERA1"], header1["CENTERA2"]))
            sizaxis = oops.Pair((header1["SIZAXIS1"], header1["SIZAXIS2"]))
            binaxis = oops.Pair((header1["BINAXIS1"], header1["BINAXIS2"]))

        # If subarrays are unsupported...
        except KeyError:
            return fov

        if (sizaxis != naxis):
            warnings.warn("FITS header warning: SIZAXIS " +
                          str((sizaxis.vals[0], sizaxis.vals[1])) +
                          " != NAXIS " +
                          str((naxis.vals[1], naxis.vals[1])))

        # Apply the subarray correction
        subarray_fov = oops.fov.Subarray(fov, centera,              # new_los
                                              naxis,                # uv_shape
                                              crpix * binaxis)      # uv_los

        # Apply the subsampling if necessary
        if binaxis == (1,1):
            return subarray_fov
        else:
            return oops.fov.Subsampled(subarray_fov, binaxis)

    ############################################################################
    # SYN (filter bandpass and instrument throughput) support functions
    ############################################################################

    def set_syn_path(self, syn_path):
        """Defines the directory path to the root directory of the SYN files.
        The alternative is to define the environment variable HST_SYN_PATH.
        """

        global HST_SYN_PATH

        HST_SYN_PATH = syn_path

    def get_syn_path(self):
        """Returns the directory path to the root directory of the SYN files. It
        uses the value of environment variable HST_SYN_PATH if the value is
        currently undefined.
        """

        global HST_SYN_PATH

        if HST_SYN_PATH is None:
            self.set_syn_path(os.environ["HST_SYN_PATH"])

        return HST_SYN_PATH

    def load_syn_throughput(self, hst_file):
        """Returns a Tabulation of throughput vs. wavelength in Angstroms for
        the combined set of SYN files returned by self.select_syn_files().
        """

        # Multiply all the Tabulations of throughputs
        syn_filenames = self.select_syn_files(hst_file)

        tabulation = self._load_syn_file(syn_filenames[0])
        for syn_filename in syn_filenames[1:]:
            tabulation *= self._load_syn_file(syn_filename)

        return tabulation

    def _load_syn_file(self, syn_filename):
        """Private function to return a Tabulation of throughput vs. wavelength
        in Angstroms for a single HST SYN file.
        """

        # Construct the full file path
        syn_pattern = os.path.join(self.get_syn_path(), syn_filename)

        # Find the most recent file
        filespec_list = glob.glob(syn_pattern)
        filespec_list.sort()

        try:
            syn_filespec = filespec_list[-1]
        except IndexError:
            raise IOError("file not found: " + syn_filename)

        # Read the tabulation and return
        syn_file = pyfits.open(syn_filespec)

        x = syn_file[1].data.WAVELENGTH
        y = syn_file[1].data.THROUGHPUT

        syn_file.close()

        return tab.Tabulation(x,y)

    def solar_f(self, hst_file, sun_range=1., model="STIS"):
        """Returns the solar F averaged over the instrument throughput.

        Input:
            bandpass        the instrument/detector/filter throughput, tabulated
                            in units of Angstroms.
            hst_file        the object returned by pyfits.open().
            sun_range       the distance from the Sun to the target in AU.
            model           the solar model, "STIS" or "COLINA"; "STIS" is the
                            default.

        Return:             solar F in units of erg/s/cm^2/Angstrom.
        """

        # Convert bandpass tabulation from Angstroms to microns
        bandpass = self.load_syn_throughput(hst_file)
        bandpass = tab.Tabulation(bandpass.x * 1.e-4, bandpass.y)

        # Convert units of solar F back to CGS per Angstrom
        solar_f_mks_per_micron = solar.bandpass_f(bandpass, sun_range, model)

        return solar_f_mks_per_micron * solar.TO_CGS * solar.TO_PER_ANGSTROM

    def compare_pivot_mean(self, hst_file):
        """Returns a tuple containing the pivot wavelength as derived from the
        SYN file and that extracted directly from the file header. They should
        be nearly equal. Both are given in units of Angstroms."""

        return (self.load_syn_throughput(hst_file).pivot_mean(),
                hst_file[1].header["PHOTPLAM"])
        
    def compare_bandwidth_rms(self, hst_file):
        """Returns a tuple containing the RMS bandwidth as derived from the SYN
        file and that extracted directly from the file header. They should
        be nearly equal. Both are given in units of Angstroms."""

        return (self.load_syn_throughput(hst_file).bandwidth_rms(),
                hst_file[1].header["PHOTBW"])

    ########################################

    @staticmethod
    def from_opened_fitsfile(hst_file, **parameters):
        """A general, static method to return an Observation object based on an
        HST data file generated by the Hubble Space Telescope."""

    # Make an instance of the HST class
        this = HST()

        # Confirm that the telescope is HST
        if this.telescope_name(hst_file) != "HST":
            raise IOError("not an HST file: " + this.filespec(hst_file))

        # Figure out the instrument
        instrument = this.instrument_name(hst_file)

        if instrument == "ACS":
            from oops.inst.hst.acs import ACS
            obs = ACS.from_opened_fitsfile(hst_file, **parameters)

        elif instrument == "NICMOS":
            from oops.inst.hst.nicmos import NICMOS
            obs = NICMOS.from_opened_fitsfile(hst_file, **parameters)

        elif instrument == "WFC3":
            from oops.inst.hst.wfc3 import WFC3
            obs = WFC3.from_opened_fitsfile(hst_file, **parameters)

        elif instrument == "WFPC2":
            from oops.inst.hst.wfpc2 import WFPC2
            obs = WFPC2.from_opened_fitsfile(hst_file, **parameters)

        else:
            raise IOError("unsupported instrument in HST file " +
                          this.filespec(hst_file) + ": " + instrument)

        return obs

################################################################################
# UNIT TESTS
################################################################################

class Test_HST(unittest.TestCase):

    def runTest(self):

        import cspice
        from oops.inst.hst.acs.hrc import HRC

        APR = 180./np.pi * 3600.

        prefix = "test_data/hst/"
        snapshot = from_file(prefix + "ibht07svq_drz.fits")
        self.assertEqual(snapshot.instrument, "WFC3")
        self.assertEqual(snapshot.detector, "IR")

        snapshot = from_file(prefix + "ibht07svq_ima.fits")
        self.assertEqual(snapshot.instrument, "WFC3")
        self.assertEqual(snapshot.detector, "IR")

        snapshot = from_file(prefix + "ibht07svq_raw.fits")
        self.assertEqual(snapshot.instrument, "WFC3")
        self.assertEqual(snapshot.detector, "IR")

        snapshot = from_file(prefix + "ibu401nnq_flt.fits")
        self.assertEqual(snapshot.instrument, "WFC3")
        self.assertEqual(snapshot.detector, "UVIS")

        snapshot = from_file(prefix + "j9dh35h7q_raw.fits")
        self.assertEqual(snapshot.instrument, "ACS")
        self.assertEqual(snapshot.detector, "HRC")

        snapshot = from_file(prefix + "j96o01ioq_raw.fits")
        self.assertEqual(snapshot.instrument, "ACS")
        self.assertEqual(snapshot.detector, "WFC")

        snapshot = from_file(prefix + "n43h05b3q_raw.fits")
        self.assertEqual(snapshot.instrument, "NICMOS")
        self.assertEqual(snapshot.detector, "NIC2")

        snapshot = from_file(prefix + "ua1b0309m_d0m.fits", {"layer":2})
        self.assertEqual(snapshot.instrument, "WFPC2")
        self.assertEqual(snapshot.detector, "")
        self.assertEqual(snapshot.layer, 2)

        snapshot = from_file(prefix + "ua1b0309m_d0m.fits", {"layer":3})
        self.assertEqual(snapshot.instrument, "WFPC2")
        self.assertEqual(snapshot.detector, "")
        self.assertEqual(snapshot.layer, 3)

        self.assertRaises(IOError, from_file, prefix + "ua1b0309m_d0m.fits",
                                              {"mask":"required"})

        self.assertRaises(IOError, from_file, prefix + "a.b.c.d")

        # Raw ACS/HRC, full-frame with overscan pixels
        filespec = "test_data/hst/j9dh35h7q_raw.fits"
        snapshot = from_file(filespec)
        hst_file = pyfits.open(filespec)
        self.assertEqual(snapshot.filter, "F475W")
        self.assertEqual(snapshot.detector, "HRC")

        # Test time_limits()
        (time0, time1) = HST().time_limits(hst_file)

        self.assertTrue(time1 - time0 - hst_file[0].header["EXPTIME"] > -1.e-8)
        self.assertTrue(time1 - time0 - hst_file[0].header["EXPTIME"] <  1.e-8)

        str0 = cspice.et2utc(time0, "ISOC", 0)
        self.assertEqual(str0, hst_file[0].header["DATE-OBS"] + "T" +
                               hst_file[0].header["TIME-OBS"])

        # Test get_fov()
        fov = HRC().define_fov(hst_file)
        shape = tuple(fov.uv_shape.vals)
        buffer = np.empty(shape + (2,))
        buffer[:,:,0] = np.arange(shape[0])[..., np.newaxis] + 0.5
        buffer[:,:,1] = np.arange(shape[1]) + 0.5
        pixels = oops.Pair(buffer)

        self.assertTrue(np.all(fov.uv_is_inside(pixels)))

        # Confirm that a fov.Polynomial is reversible

        # This is SLOW for a million pixels but it works. I have done a bit of
        # optimization and appear to have reached the point of diminishing
        # returns.

        # los = fov.los_from_uv(pixels)
        # test_pixels = fov.uv_from_los(los)

        # Faster version, 1/64 pixels
        NSTEP = 256
        pixels = oops.Pair(buffer[::NSTEP,::NSTEP])
        los = fov.los_from_uv(pixels)
        test_pixels = fov.uv_from_los(los)

        self.assertTrue(abs(test_pixels - pixels).max() < 1.e-7)

        # Separations between pixels in arcsec are around 0.025
        seps = los[1:].sep(los[:-1])
        self.assertTrue(np.min(seps.vals) * APR > 0.028237 * NSTEP)
        self.assertTrue(np.max(seps.vals) * APR < 0.028648 * NSTEP)

        seps = los[:,1:].sep(los[:,:-1])
        self.assertTrue(np.min(seps.vals) * APR > 0.024547 * NSTEP)
        self.assertTrue(np.max(seps.vals) * APR < 0.025186 * NSTEP)

        # Pixel area factors are near unity
        areas = fov.area_factor(pixels)
        self.assertTrue(np.min(areas.vals) > 1.102193)
        self.assertTrue(np.max(areas.vals) < 1.149735)

########################################
if __name__ == '__main__':
    unittest.main(verbosity=2)
################################################################################
