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
    """Manages system-wide media playback and audio output muting directly via macOS CoreAudio & MediaRemote."""

    _ca = None
    _mr = None
    _out_dev: Optional[int] = None
    _addr_mute: Optional[AudioObjectPropertyAddress] = None
    _was_already_muted: bool = False
    _is_muted_by_us: bool = False
    _paused_media_by_us: bool = False

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
            except Exception:
                cls._ca = False

        if cls._mr is None:
            try:
                cls._mr = ctypes.cdll.LoadLibrary("/System/Library/PrivateFrameworks/MediaRemote.framework/MediaRemote")
                cls._mr.MRMediaRemoteSendCommand.argtypes = [ctypes.c_int32, ctypes.c_void_p]
                cls._mr.MRMediaRemoteSendCommand.restype = ctypes.c_bool
            except Exception:
                cls._mr = False

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
        """Immediately pauses media playback via macOS MediaRemote and mutes hardware output for instant silence."""
        cls._init()

        # 1. Send system-wide Media Remote Pause command (kMRPause = 1)
        if cls._mr:
            try:
                res = cls._mr.MRMediaRemoteSendCommand(1, None)
                if res:
                    cls._paused_media_by_us = True
            except Exception:
                pass

        # 2. Hardware-level output mute as zero-latency backstop
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
        return True

    @classmethod
    def resume(cls) -> bool:
        """Restores hardware audio output volume and resumes media playback if paused by us."""
        cls._init()

        # 1. Unmute hardware audio
        if cls._ca and cls._is_muted_by_us and cls._addr_mute:
            try:
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

        # 2. Resume media playback via macOS MediaRemote (kMRPlay = 0)
        if cls._mr and cls._paused_media_by_us:
            try:
                cls._mr.MRMediaRemoteSendCommand(0, None)
                cls._paused_media_by_us = False
            except Exception:
                pass

        return True
