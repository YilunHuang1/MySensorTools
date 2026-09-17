"""Compatibility import for the ROS-independent serial handler.

Measurements are written to CSV; this adapter does not impersonate the robot's
production uwb/ranging publisher. For passive robot checks use smoke_test online.
"""
from SerialHandlerStandalone import SerialHandler

__all__ = ['SerialHandler']
