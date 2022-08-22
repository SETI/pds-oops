################################################################################
# oops/format_/format.py: Abstract class Format
################################################################################

#*******************************************************************************
# Format
#*******************************************************************************
class Format(object):
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    """
    A generic class for converting numeric values to/from strings.
    """
    #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
    OOPS_CLASS = "Format"

    #===========================================================================
    # __init__
    #===========================================================================
    def __init__(self):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        The constructor for a Format object
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        pass
    #===========================================================================



    #===========================================================================
    # str
    #===========================================================================
    def str(self, value):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
       Returns a character string indicating the value of a numeric quantity.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        pass
    #===========================================================================



    #===========================================================================
    # parse
    #===========================================================================
    def parse(self, string):
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        """
        Returns a numeric value interpreted from a character string.
        """
        #+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
        pass
    #===========================================================================


#*******************************************************************************



################################################################################
# UNIT TESTS
################################################################################

import unittest

#*******************************************************************************
# Test_Format
#*******************************************************************************
class Test_Format(unittest.TestCase):

    #===========================================================================
    # runTest
    #===========================================================================
    def runTest(self):

        # No tests here - this is just an abstract superclass

        pass
    #===========================================================================


#*******************************************************************************


########################################
if __name__ == '__main__':
    unittest.main(verbosity=2)
################################################################################
