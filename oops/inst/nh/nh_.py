################################################################################
# oops/inst/nh/nh_.py
#
# Utility functions for managing SPICE kernels while working with NewHorizons
# data sets.
################################################################################

import numpy as np
import unittest
import os.path

import julian
import textkernel
import spicedb
import oops

#*******************************************************************************
# NewHorizons
#*******************************************************************************
class NewHorizons(object):
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    """
    A instance-free class to hold NewHorizons-specific parameters.
    """
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    START_TIME = '2006-10-01'
    STOP_TIME  = '2018-01-01'

    initialized = False
    time = [START_TIME, STOP_TIME]
    asof = np.nan       # placeholder value ensuring first call
    meta = None
    names = []

    ############################################################################

    #===========================================================================
    # initialize
    #===========================================================================
    @staticmethod
    def initialize(asof=None, time=None, meta=None):
        if time is None: time = NewHorizons.time

        if NewHorizons.initialized and \
           NewHorizons.asof == asof and \
           NewHorizons.meta == meta and \
           NewHorizons.time[0] <= time[0] and NewHorizons.time[1] >= time[1]:
                return NewHorizons.names

        #------------------------
        # Load SPICE kernels
        #------------------------
        if meta is None:
            ignore = oops.define_solar_system(NewHorizons.START_TIME,
                                              NewHorizons.STOP_TIME,
                                              asof=asof)

            spicedb.open_db()

            names = spicedb.furnish_lsk(asof=asof)
            names = spicedb.furnish_pck([5,9] + range(501,505) +
                                                range(514,517) +
                                                range(901,906), asof=asof)

            names += spicedb.furnish_inst(-98, asof=asof)

            names += spicedb.furnish_spk(-98, time=time,
                                              name='NH-SPK-PREDICTED%',
                                              asof=asof)

            names += spicedb.furnish_spk(-98, time=time,
                                              name='NH-SPK-RECONSTRUCTED%',
                                              asof=asof)

            names += spicedb.furnish_ck(-98, time=time, asof=asof)

        else:
            spicedb.open_db()
            names = spicedb.furnish_by_metafile(meta, time=time, asof=asof)

        spicedb.close_db()

        NewHorizons.initialized = True
        NewHorizons.time = time
        NewHorizons.asof = asof
        NewHorizons.meta = meta
        NewHorizons.names = names

        ignore = oops.path.SpicePath('NEW HORIZONS', 'JUPITER')
        ignore = oops.path.SpicePath('NEW HORIZONS', 'PLUTO')

        return names
    #===========================================================================



    #===========================================================================
    # reset
    #===========================================================================
    @staticmethod
    def reset():
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Resets the internal parameters. Can be useful for debugging.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        spicedb.unload_by_name(NewHorizons.names)

        NewHorizons.loaded_instruments = []
        NewHorizons.initialized = False
        NewHorizons.asof = None
        NewHorizons.names = []
    #===========================================================================



    ############################################################################
    # Routines for managing text kernel information
    ############################################################################

    #===========================================================================
    # spice_instrument_kernel
    #===========================================================================
    @staticmethod
    def spice_instrument_kernel(inst_name, asof=None):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Return a dictionary containing the Instrument Kernel information.

        It also furnishes it for use by the SPICE tools.

        Input:
            inst_name   one of "LORRI", etc.
            asof        an optional date in the past, in ISO date or date-time
                        format. If provided, then the information provided will
                        be applicable as of that date. Otherwise, the most
                        recent information is always provided.

        Return:         a tuple containing:
                            the dictionary generated by textkernel.from_file()
                            the name of the kernel.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        spicedb.open_db()
        kernel_info = spicedb.select_inst(-98, inst=inst_name.lower(),
                                               types="IK", asof=asof)
        spicedb.furnish_kernels(kernel_info)
        spicedb.close_db()

        return (spicedb.as_dict(kernel_info), spicedb.as_names(kernel_info))
    #===========================================================================



    #===========================================================================
    # spice_frames_kernel
    #===========================================================================
    @staticmethod
    def spice_frames_kernel(asof=None):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Return a dictionary containing the Cassini Frames Kernel information.

        Also furnishes the kernels for use by the SPICE tools.

        Input:
            asof        an optional date in the past, in ISO date or date-time
                        format. If provided, then the information provided will
                        be applicable as of that date. Otherwise, the most
                        recent information is always provided.

        Return:         a tuple containing:
                            the dictionary generated by textkernel.from_file()
                            an ordered list of the names of the kernels
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        spicedb.open_db()
        kernel_info = spicedb.select_inst(-98, inst=inst_name, types="FK",
                                               asof=asof)
        spicedb.furnish_kernels(kernel_info)
        spicedb.close_db()

        return (spicedb.as_dict(kernel_info), spicedb.as_names(kernel_info)[0])
    #===========================================================================



#*******************************************************************************



################################################################################
