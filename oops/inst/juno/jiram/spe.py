################################################################################
# oops/inst/juno/jiram/spe.py
################################################################################

from IPython import embed   ## TODO: remove

import numpy as np
import julian
import pdstable
import cspyce
import oops
from polymath import *
import os.path
import pdsparser

from oops.inst.juno.juno_ import Juno
from oops.inst.juno.jiram import JIRAM

################################################################################
# Standard class methods
################################################################################

#===============================================================================
# from_file
#===============================================================================
def from_file(filespec, label, fast_distortion=True,
              return_all_planets=False, **parameters):
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    """
    A general, static method to return a Snapshot object based on a given
    JIRAM image or spectrum file.

    Inputs:
        fast_distortion     True to use a pre-inverted polynomial;
                            False to use a dynamically solved polynomial;
                            None to use a FlatFOV.

        return_all_planets  Include kernels for all planets not just
                            Jupiter or Saturn.
    """
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

    #---------------------------------
    # Get metadata 
    #---------------------------------
    meta = Metadata(label)

    #--------------------------------------------
    # Define everything the first time through
    #--------------------------------------------
    SPE.initialize(meta.tstart)

    #------------------------------------------------------------------
    # Load the data array as separate framelets, with associated labels
    #------------------------------------------------------------------
    data = _load_data(filespec, label, meta)

    #-------------------------------------------
    # Construct Snapshots for slit in each band 
    #-------------------------------------------
    slits = []
    for i in range(meta.nsamples):
        item = oops.obs.Snapshot(("v","u"), 
                             (meta.tstart, meta.exposure), meta.fov_slits,
                             "JUNO", "JUNO_JIRAM_S", 
                             data=np.reshape(data[:,i],(1,meta.nlines)) )
                             
#        item.insert_subfield('spice_kernels', \
#                   Juno.used_kernels(item.time, 'jiram', return_all_planets))
        item.insert_subfield('filespec', filespec)
        item.insert_subfield('basename', os.path.basename(filespec))
        slits.append(item)

#    return slits


    #-------------------------------------------
    # Construct Snapshot for all bands 
    #-------------------------------------------
    obs = oops.obs.Snapshot(("v","u","b"), 
                         (meta.tstart, meta.exposure), meta.fov,
                         "JUNO", "JUNO_JIRAM_S", data=data )
                         
#    obs.insert_subfield('spice_kernels', \
#               Juno.used_kernels(item.time, 'jiram', return_all_planets))
    obs.insert_subfield('filespec', filespec)
    obs.insert_subfield('basename', os.path.basename(filespec))


    return (obs, slits)

#===============================================================================



#===============================================================================
# _load_data
#===============================================================================
def _load_data(filespec, label, meta):
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    """
    Loads the data array from the file and splits into individual framelets. 

    Input:
        filespec        Full path to the data file.
        label           Label for composite image.
        meta            Image Metadata object.

    Return:             (framelets, framelet_labels)
        framelets       A Numpy array containing the individual frames in 
                        axis order (line, sample, framelet #).
        framelet_labels List of labels for each framelet.
    """
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    
    #----------------
    # Read data 
    #----------------
    # seems like this should be handled in a readpds-style function somewhere
    data = np.fromfile(filespec, dtype='<f4').reshape(meta.nlines,meta.nsamples)

    return(data)
#===============================================================================



#*******************************************************************************
# Metadata 
#*******************************************************************************
class Metadata(object):

    #===========================================================================
    # __init__
    #===========================================================================
    def __init__(self, label):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Uses the label to assemble the image metadata.

        Input:
            label           The label dictionary.

        Attributes:         
            nlines          A Numpy array containing the data in axis order
                            (line, sample).
            nsamples        The time sampling array in (line, sample) axis 
                            order, or None if no time backplane is found in 
                            the file.

        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

        #---------------------
        # dimensions
        #---------------------
        self.nlines = label['FILE']['TABLE']['ROWS']
        self.nsamples = label['FILE']['TABLE']['COLUMNS']

        #-----------------
        # Exposure time
        #-----------------
        self.exposure = label['EXPOSURE_DURATION']

        #--------------------
        # Default timing 
        #--------------------
        self.tstart = julian.tdb_from_tai(
                        julian.tai_from_iso(label['START_TIME']))
        self.tstop = julian.tdb_from_tai(
                       julian.tai_from_iso(label['STOP_TIME']))

        #-------------
        # target
        #-------------
        self.target = label['TARGET_NAME']

        #--------------------
        # Kernel FOV params
        #--------------------
        cross_angle = cspyce.gdpool('INS-61420_FOV_CROSS_ANGLE', 0)[0]
        fo = cspyce.gdpool('INS-61420_FOCAL_LENGTH', 0)[0]
        px = cspyce.gdpool('INS-61420_PIXEL_SIZE', 0)[0]
        cxy = cspyce.gdpool('INS-61420_CCD_CENTER', 0)
        scale = px/1000/fo

        #-------------
        # FOVs
        #-------------
        self.fov_slits = oops.fov.FlatFOV(scale, (self.nlines, 1), cxy)
        self.fov = oops.fov.FlatFOV(scale, (self.nlines, self.nsamples), 
                                                   [cxy[0], self.nsamples/2])

        return
    #===========================================================================

#*******************************************************************************



#*******************************************************************************
# SPE 
#*******************************************************************************
class SPE(object):
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    """
    A instance-free class to hold SPE instrument parameters.
    """
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

    initialized = False

    #===========================================================================
    # initialize
    #===========================================================================
    @staticmethod
    def initialize(time, ck='reconstructed', planets=None, asof=None,
               spk='reconstructed', gapfill=True,
               mst_pck=True, irregulars=True):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Initialize key information about the SPE instrument.

        Must be called first. After the first call, later calls to this function
        are ignored.

        Input:
            time        time at which to define the inertialy fixed mirror-
                        corrected frame.
            ck,spk      'predicted', 'reconstructed', or 'none', depending on which
                        kernels are to be used. Defaults are 'reconstructed'. Use
                        'none' if the kernels are to be managed manually.
            planets     A list of planets to pass to define_solar_system. None or
                        0 means all.
            asof        Only use SPICE kernels that existed before this date; None
                        to ignore.
            gapfill     True to include gapfill CKs. False otherwise.
            mst_pck     True to include MST PCKs, which update the rotation models
                        for some of the small moons.
            irregulars  True to include the irregular satellites;
                        False otherwise.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

        #------------------------------------
        # Quick exit after first call
        #------------------------------------
        if SPE.initialized: return

        #------------------------------------
        # initialize JIRAM
        #------------------------------------
        JIRAM.initialize(ck=ck, planets=planets, asof=asof,
                     spk=spk, gapfill=gapfill,
                     mst_pck=mst_pck, irregulars=irregulars)

        #-----------------------------------
        # Construct the SpiceFrame
        #-----------------------------------
        JIRAM.create_frame(time, 'S')


        SPE.initialized = True
    #===========================================================================



    #===========================================================================
    # reset
    #===========================================================================
    @staticmethod
    def reset():
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Resets the internal SPE parameters. Can be useful for
        debugging.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        SPE.initialized = False

        JIRAM.reset()
    #============================================================================

#*****************************************************************************


