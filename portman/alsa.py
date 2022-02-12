#!/usr/bin/env python3
import subprocess
from typing import (
    Dict, Tuple
)

import alsaaudio
from portman.base import SimpleEqMixin, KeyedEqMixin


class AmixerTrackBase(SimpleEqMixin):
    def __init__(self, card_index: int, control_name: str) -> None:
        self.card_index = card_index
        self.control_name = control_name

    def _get_lines(self) -> Dict[str, str]:
        lines = subprocess.check_output(
            ("amixer", "-c1", "sget", "%s,0" % self.control_name),
            universal_newlines=True,
        ).splitlines()
        assert lines[0].startswith("Simple mixer control")
        return {k: v for line in lines[1:] for k, v in [line.strip().split(": ", 1)]}

    def _set(self, s: str) -> None:
        subprocess.check_call(
            ("amixer", "-c1", "sset", "%s,0" % self.control_name, s),
            stdout=subprocess.DEVNULL,
        )


class AmixerEnumTrack(AmixerTrackBase):
    def __init__(
        self, card_index: int, control_name: str, off_setting: str, on_setting: str
    ) -> None:
        super().__init__(card_index, control_name)
        self.off_setting = off_setting
        self.on_setting = on_setting

    def get(self) -> bool:
        return self._get_lines()["Item0"] == "'%s'" % self.on_setting

    def set(self, v: bool) -> None:
        self._set(self.on_setting if v else self.off_setting)

    def __repr__(self) -> str:
        return f"<AmixerEnumTrack control_name={self.control_name} off={self.off_setting} on={self.on_setting}>"

    def print(self, c: str) -> None:
        print(c, self.control_name, self.on_setting, self.off_setting, end="\r\n")


class AmixerVolumeTrack(AmixerTrackBase):
    def __init__(self, card_index: int, control_name: str, on_setting: int) -> None:
        super().__init__(card_index, control_name)
        self.off_setting = 0
        self.on_setting = on_setting

    def get(self) -> bool:
        return int(self._get_lines()["Mono"].split()[1]) == self.on_setting

    def set(self, v: bool) -> None:
        self._set(str(self.on_setting if v else self.off_setting))

    def __repr__(self) -> str:
        return f"<AmixerVolumeTrack control_name={self.control_name} off={self.off_setting} on={self.on_setting}>"

    def print(self, c: str) -> None:
        print(c, self.control_name, self.on_setting, self.off_setting, end="\r\n")


_mixers: Dict[Tuple[int, str], alsaaudio.Mixer] = {}


def _get_mixer(card_index: int, control_name: str) -> alsaaudio.Mixer:
    try:
        return _mixers[card_index, control_name]
    except KeyError:
        _mixers[card_index, control_name] = m = alsaaudio.Mixer(
            cardindex=card_index, control=control_name
        )
        return m


class PyalsaaudioEnumTrack(KeyedEqMixin):
    def __init__(
        self, card_index: int, control_name: str, off_setting: str, on_setting: str
    ) -> None:
        self.key = (card_index, control_name, off_setting, on_setting)
        self.card_index = card_index
        self.control_name = control_name
        self.mixer = _get_mixer(card_index, control_name)
        self.off_setting = off_setting
        self.on_setting = on_setting

    def get(self) -> bool:
        return self.mixer.getenum()[0] == self.on_setting

    def set(self, v: bool) -> None:
        c, vs = self.mixer.getenum()
        try:
            i = vs.index(self.on_setting if v else self.off_setting)
            self.mixer.setenum(i)
        except alsaaudio.ALSAAudioError:
            print(self.key, v, i, c, vs)
            raise

    def __repr__(self) -> str:
        args = ", ".join(
            "%s=%r" % (k, getattr(self, k))
            for k in "card_index control_name off_setting on_setting".split()
        )
        return f"{self.__class__.__name__}({args})"

    def print(self, c: str) -> None:
        print(c, self.control_name, self.on_setting, self.off_setting, end="\r\n")


class PyalsaaudioVolumeTrack(KeyedEqMixin):
    def __init__(self, card_index: int, control_name: str, on_setting: int) -> None:
        self.key = (card_index, control_name, on_setting)
        self.card_index = card_index
        self.control_name = control_name
        self.mixer = _get_mixer(card_index, control_name)
        self.off_setting = 0
        self.on_setting = on_setting

    def get(self) -> bool:
        v = self.mixer.getvolume()[0]
        return v == self.on_setting

    def set(self, v: bool) -> None:
        self.mixer.setvolume(self.on_setting if v else self.off_setting)

    def __repr__(self) -> str:
        args = ", ".join(
            "%s=%r" % (k, getattr(self, k))
            for k in "card_index control_name on_setting".split()
        )
        return f"{self.__class__.__name__}({args})"

    def print(self, c: str) -> None:
        print(c, self.control_name, self.on_setting, self.off_setting, end="\r\n")
