class PyVRPException(Exception):
    """Base exception for PyVRP."""
    pass

class ScalingException(PyVRPException):
    """Raised when scaling issues occur."""
    pass