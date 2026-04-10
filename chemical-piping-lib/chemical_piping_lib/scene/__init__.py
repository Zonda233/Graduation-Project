"""
scene
=====
Scene-assembly layer: JSON parsing, asset dispatching, collection management,
and port registration.

This layer is the only one that is allowed to call asset constructors.
The ``utils`` and ``assets`` layers know nothing about this layer.
"""
