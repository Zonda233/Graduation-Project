"""
registry.py
===========
Global port registry for a single build session.

Every asset that is successfully built registers its ports here.
The assembler and optional validation steps can then query port positions
without needing to retain references to individual asset instances.

Thread safety
-------------
Blender Python is single-threaded; no locking is needed.

Lifecycle
---------
Call :meth:`PortRegistry.clear` at the start of each :func:`~api.build_from_json`
invocation so that stale data from a previous build does not interfere.
"""

from __future__ import annotations

import logging

from mathutils import Vector

log = logging.getLogger(__name__)

# Tolerance for port-alignment validation (metres).
_DEFAULT_TOLERANCE = 0.01


class PortRegistry:
    """
    Singleton-like class (all methods are class-methods) that stores a
    flat mapping of ``port_id -> world-space Vector``.
    """

    _ports: dict[str, Vector] = {}

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @classmethod
    def register(cls, port_id: str, wc: Vector) -> None:
        """
        Register a port.

        Parameters
        ----------
        port_id: Unique string identifier (e.g. ``"tank_01_nozzle_top"``).
        wc:      World-space position of the port.
        """
        if port_id in cls._ports:
            log.warning(
                "PortRegistry.register: port_id %r already registered; overwriting.",
                port_id,
            )
        cls._ports[port_id] = wc.copy()
        log.debug("PortRegistry.register: %r @ %s", port_id, wc)

    @classmethod
    def register_many(cls, ports: dict[str, Vector]) -> None:
        """Register multiple ports from a ``{port_id: Vector}`` dict."""
        for pid, wc in ports.items():
            cls.register(pid, wc)

    @classmethod
    def clear(cls) -> None:
        """Flush all registered ports.  Call before each build."""
        cls._ports.clear()
        log.debug("PortRegistry.clear: registry flushed.")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, port_id: str) -> Vector | None:
        """
        Return the registered world position for *port_id*, or ``None``
        if it has not been registered.
        """
        return cls._ports.get(port_id)

    @classmethod
    def all_ports(cls) -> dict[str, Vector]:
        """Return a shallow copy of the entire registry."""
        return dict(cls._ports)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @classmethod
    def validate_connection(
        cls,
        port_a_id: str,
        port_b_id: str,
        tolerance: float = _DEFAULT_TOLERANCE,
    ) -> bool:
        """
        Check that two registered ports are within *tolerance* metres of
        each other.

        Logs a WARNING if misaligned; logs DEBUG if aligned.

        Parameters
        ----------
        port_a_id: First port id.
        port_b_id: Second port id.
        tolerance: Acceptable distance (metres).  Default 10 mm.

        Returns
        -------
        ``True`` if both ports exist and are within tolerance.
        ``False`` otherwise.
        """
        wc_a = cls.get(port_a_id)
        wc_b = cls.get(port_b_id)

        if wc_a is None:
            log.warning(
                "PortRegistry.validate_connection: port_id %r not found.", port_a_id
            )
            return False
        if wc_b is None:
            log.warning(
                "PortRegistry.validate_connection: port_id %r not found.", port_b_id
            )
            return False

        dist = (wc_a - wc_b).length
        if dist > tolerance:
            log.warning(
                "PortRegistry.validate_connection: %r and %r are %.4f m apart "
                "(tolerance %.4f m). Check route coordinates.",
                port_a_id, port_b_id, dist, tolerance,
            )
            return False

        log.debug(
            "PortRegistry.validate_connection: %r ↔ %r OK (%.4f m).",
            port_a_id, port_b_id, dist,
        )
        return True
