#!/usr/bin/env python3
import string
from typing import (
    List,
    Optional,
)

import pyscarlett
from portman.base import MultiConnectionTrack, ConnectionTrackProtocol
from portman.alsa import PyalsaaudioEnumTrack, PyalsaaudioVolumeTrack 


class Scarlett:
    def __init__(self) -> None:
        self.channels = pyscarlett.get_channels()
        self.card_index = self.channels["card_index"]
        self.pcms = self.channels["pcms"]
        self.inputs = self.channels["inputs"]
        self.outputs = self.channels["outputs"]
        self.mixes = self.channels["mixes"]

    def set_analogue_outputs(self, *args: Optional[str]) -> ConnectionTrackProtocol:
        assert len(args) == self.outputs
        switches = [
            self.switch_analogue_output(i, s)
            for i, s in enumerate(args)
            if s is not None
        ]
        return MultiConnectionTrack(*switches)

    def set_pcm_outputs(self, *args: Optional[str]) -> ConnectionTrackProtocol:
        assert len(args) == self.pcms
        switches = [
            self.switch_pcm_output(i, s) for i, s in enumerate(args) if s is not None
        ]
        return MultiConnectionTrack(*switches)

    def set_mixer_inputs(self, *args: Optional[str]) -> ConnectionTrackProtocol:
        assert len(args) == self.inputs
        switches = [
            self.switch_mixer_input(i, s)
            for i, s in enumerate(args, 1)
            if s is not None
        ]
        return MultiConnectionTrack(*switches)

    def set_mix(
        self, inputs: List[Optional[str]], *args: List[Optional[int]]
    ) -> ConnectionTrackProtocol:
        assert len(inputs) == self.inputs
        assert len(args) == self.inputs
        assert all(len(a) == self.mixes for a in args)
        switches = [
            self.switch_mix(c, i, v)
            for i, a in enumerate(args, 1)
            for c, v in zip(string.ascii_uppercase, a)
            if v is not None
        ]
        return MultiConnectionTrack(self.set_mixer_inputs(*inputs), *switches)

    def switch_analogue_output(
        self, output_index: int, on_state: str
    ) -> ConnectionTrackProtocol:
        assert 0 <= output_index < self.outputs
        return PyalsaaudioEnumTrack(
            self.card_index,
            "Analogue Output %02d" % (1 + output_index),
            "Off",
            on_state,
        )

    def switch_pcm_output(
        self, output_index: int, on_state: str
    ) -> ConnectionTrackProtocol:
        assert 0 <= output_index < self.pcms
        return PyalsaaudioEnumTrack(
            self.card_index, "PCM %02d" % (1 + output_index), "Off", on_state
        )

    def switch_mixer_input(self, inp: int, on_state: str) -> ConnectionTrackProtocol:
        assert 1 <= inp <= self.inputs
        return PyalsaaudioEnumTrack(
            self.card_index, "Mixer Input %02d" % inp, "Off", on_state
        )

    def switch_mix(
        self, mix: str, inp: int, volume: int = 100
    ) -> ConnectionTrackProtocol:
        assert 1 <= inp <= self.inputs
        assert ord("A") <= ord(mix) < ord("A") + self.mixes
        return PyalsaaudioVolumeTrack(
            self.card_index, f"Mix {mix} Input {inp:02d}", volume
        )

    def switch_mix_stereo(
        self, mixmix: str, inpinp: int, volume: int = 100
    ) -> ConnectionTrackProtocol:
        assert len(mixmix) == 2
        m, n = mixmix[0], mixmix[1]
        i, j = divmod(inpinp, 10)
        return MultiConnectionTrack(self.switch_mix(m, i, volume), self.switch_mix(n, j, volume))
