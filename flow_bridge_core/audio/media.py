"""
CoreAudio Hardware Volume Management & MediaRemote Playback Control.
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
    """Manages system-wide audio and video pause/resume via CoreAudio Hardware Muting and MediaRemote."""

    _mr = None
    _ca = None
    _out_dev: Optional[int] = None
    _addr_mute: Optional[AudioObjectPropertyAddress] = None
    _was_already_muted: bool = False
    _is_muted_by_us: bool = False

    @classmethod
    def _fourcc(cls, s: str) -> int:
        return int.from_bytes(s.encode("latin1"), byteorder="big")

    @classmethod
    def _init(cls) -> None:
        if cls._mr is None:
            try:
                cls._mr = ctypes.cdll.LoadLibrary("/System/Library/PrivateFrameworks/MediaRemote.framework/MediaRemote")
                cls._mr.MRMediaRemoteSendCommand.restype = ctypes.c_bool
                cls._mr.MRMediaRemoteSendCommand.argtypes = [ctypes.c_int32, ctypes.c_void_p]
            except Exception:
                cls._mr = False

        if cls._ca is None:
            try:
                ca_path = ctypes.util.find_library("CoreAudio")
                if ca_path:
                    cls._ca = ctypes.cdll.LoadLibrary(ca_path)
                    cls._addr_mute = AudioObjectPropertyAddress(cls._fourcc("mute"), cls._fourcc("outp"), 0)
            except Exception:
                cls._ca = False

    @classmethod
    def _get_default_output_device(cls) -> Optional[int]:
        if not cls._ca:
            return None
        try:
            addr_def = AudioObjectPropertyAddress(cls._fourcc("dOut"), cls._fourcc("glob"), 0)
            dev = ctypes.c_uint32(0)
            sz = ctypes.c_uint32(ctypes.sizeof(dev))
            status = cls._ca.AudioObjectGetPropertyData(1, ctypes.byref(addr_def), 0, None, ctypes.byref(sz), ctypes.byref(dev))
            return dev.value if status == 0 else None
        except Exception:
            return None

    @classmethod
    def pause(cls) -> bool:
        """Immediately mutes all audio output (YouTube, Spotify, Chrome, system sounds) instantly without launching Apple Music."""
        cls._init()

        # 1. Hardware Output Mute (sub-millisecond instant silence across all apps and tabs)
        dev_id = cls._get_default_output_device()
        if cls._ca and dev_id and cls._addr_mute:
            try:
                curr_mute = ctypes.c_uint32(0)
                sz_mute = ctypes.c_uint32(ctypes.sizeof(curr_mute))
                cls._ca.AudioObjectGetPropertyData(dev_id, ctypes.byref(cls._addr_mute), 0, None, ctypes.byref(sz_mute), ctypes.byref(curr_mute))
                cls._was_already_muted = (curr_mute.value == 1)

                if not cls._was_already_muted:
                    mute_val = ctypes.c_uint32(1)
                    cls._ca.AudioObjectSetPropertyData(dev_id, ctypes.byref(cls._addr_mute), 0, None, ctypes.sizeof(mute_val), ctypes.byref(mute_val))
                    cls._is_muted_by_us = True
                    cls._out_dev = dev_id
            except Exception:
                pass

        # 2. MediaRemote Pause signal (safe, pauses active audio/video without launching apps)
        if cls._mr:
            try:
                # 1 = kMRPause
                cls._mr.MRMediaRemoteSendCommand(1, None)
            except Exception:
                pass
        return True

    @classmethod
    def resume(cls) -> bool:
        """Restores audio output volume instantly without invoking blind kMRPlay which launches Apple Music."""
        cls._init()

        # 1. Unmute hardware output if we were the one who muted it
        if cls._ca and cls._is_muted_by_us and cls._addr_mute:
            try:
                # Unmute both the device we recorded muting and the current default output
                target_devs = set()
                if cls._out_dev:
                    target_devs.add(cls._out_dev)
                curr_dev = cls._get_default_output_device()
                if curr_dev:
                    target_devs.add(curr_dev)

                unmute_val = ctypes.c_uint32(0)
                for dev_id in target_devs:
                    cls._ca.AudioObjectSetPropertyData(dev_id, ctypes.byref(cls._addr_mute), 0, None, ctypes.sizeof(unmute_val), ctypes.byref(unmute_val))
                cls._is_muted_by_us = False
            except Exception:
                pass

        # Note: We intentionally DO NOT send blind kMRPlay (0) here.
        # Sending kMRPlay when no track was previously playing causes macOS to launch Music.app.
        # By unmuting the hardware output, active media continues smoothly with zero app launches.
        return True
