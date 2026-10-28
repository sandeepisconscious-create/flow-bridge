"""
CoreAudio Hardware Volume Management.
Provides instantaneous, zero-latency audio muting during dictation across all apps and tabs,
without sending any media playback commands that can cause unwanted auto-play or launch Apple Music.
"""

from __future__ import annotations

import ctypes
import ctypes.util
from typing import Optional


class AudioObjectPropertyAddress(ctypes.Structure):
    _fields_ = [
        ("mSelector", ctypes.c_uint32),
        ("mScope", ctypes.c_uint32),
        ("mElement", ctypes.c_uint32),
    ]


class MediaController:
    """Manages system-wide audio output muting directly via macOS CoreAudio."""

    _ca = None
    _addr_mute: Optional[AudioObjectPropertyAddress] = None
    _addr_def_out: Optional[AudioObjectPropertyAddress] = None
    _addr_devs: Optional[AudioObjectPropertyAddress] = None
    _muted_devices: set = set()
    _is_muted_by_us: bool = False

    @classmethod
    def _fourcc(cls, s: str) -> int:
        return int.from_bytes(s.encode("latin1"), byteorder="big")

    @classmethod
    def _init(cls) -> None:
        if cls._ca is None:
            try:
                ca_path = ctypes.util.find_library("CoreAudio")
                if ca_path:
                    cls._ca = ctypes.cdll.LoadLibrary(ca_path)
                    cls._addr_mute = AudioObjectPropertyAddress(cls._fourcc("mute"), cls._fourcc("outp"), 0)
                    cls._addr_def_out = AudioObjectPropertyAddress(cls._fourcc("dOut"), cls._fourcc("glob"), 0)
                    cls._addr_devs = AudioObjectPropertyAddress(cls._fourcc("dev#"), cls._fourcc("glob"), 0)
            except Exception:
                cls._ca = False

    @classmethod
    def _get_output_devices(cls) -> set[int]:
        """Returns all audio output device IDs capable of hardware muting."""
        cls._init()
        if not cls._ca or not cls._addr_mute:
            return set()

        dev_ids = set()
        # 1. Default system output device
        try:
            dev = ctypes.c_uint32(0)
            sz = ctypes.c_uint32(ctypes.sizeof(dev))
            status = cls._ca.AudioObjectGetPropertyData(1, ctypes.byref(cls._addr_def_out), 0, None, ctypes.byref(sz), ctypes.byref(dev))
            if status == 0 and dev.value:
                dev_ids.add(dev.value)
        except Exception:
            pass

        # 2. Enumerate all audio devices on the system
        try:
            sz_all = ctypes.c_uint32(0)
            status = cls._ca.AudioObjectGetPropertyDataSize(1, ctypes.byref(cls._addr_devs), 0, None, ctypes.byref(sz_all))
            if status == 0 and sz_all.value > 0:
                num = sz_all.value // ctypes.sizeof(ctypes.c_uint32)
                buf = (ctypes.c_uint32 * num)()
                status = cls._ca.AudioObjectGetPropertyData(1, ctypes.byref(cls._addr_devs), 0, None, ctypes.byref(sz_all), buf)
                if status == 0:
                    for d in buf:
                        is_settable = ctypes.c_uint32(0)
                        ca_res = cls._ca.AudioObjectIsPropertySettable(d, ctypes.byref(cls._addr_mute), ctypes.byref(is_settable))
                        if ca_res == 0 and is_settable.value:
                            dev_ids.add(d)
        except Exception:
            pass

        return dev_ids

    @classmethod
    def pause(cls) -> bool:
        """Immediately mutes macOS hardware audio output (sub-millisecond instant silence)."""
        cls._init()
        if not cls._ca or not cls._addr_mute:
            return False

        devices = cls._get_output_devices()
        mute_val = ctypes.c_uint32(1)
        for dev_id in devices:
            try:
                cls._ca.AudioObjectSetPropertyData(
                    dev_id, ctypes.byref(cls._addr_mute), 0, None, ctypes.sizeof(mute_val), ctypes.byref(mute_val)
                )
                cls._muted_devices.add(dev_id)
            except Exception:
                pass

        cls._is_muted_by_us = True
        return True

    @classmethod
    def resume(cls, force: bool = False) -> bool:
        """
        Unmutes hardware audio output cleanly across all output devices.
        If force=True, forces all settable devices to unmuted state even if flag was cleared.
        """
        cls._init()
        if not cls._ca or not cls._addr_mute:
            return False

        if not cls._is_muted_by_us and not force:
            return True

        devices = cls._get_output_devices() | cls._muted_devices
        unmute_val = ctypes.c_uint32(0)
        for dev_id in devices:
            try:
                cls._ca.AudioObjectSetPropertyData(
                    dev_id, ctypes.byref(cls._addr_mute), 0, None, ctypes.sizeof(unmute_val), ctypes.byref(unmute_val)
                )
            except Exception:
                pass

        cls._muted_devices.clear()
        cls._is_muted_by_us = False
        return True
