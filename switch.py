from typing import Dict

from portman.jack import PortManJack as PortMan
from portman.base import (
    ConnectionTrackProtocol,
    MultiConnectionTrack,
)
from portman.scarlett import Scarlett
from portman.tui import tuiwrapper, TuiConf


@tuiwrapper
def main(pm: PortMan) -> TuiConf:
    scarlett = Scarlett()
    MultiConnectionTrack(
        # PCM outputs:
        scarlett.set_pcm_outputs(
            "Analogue 1",
            "Analogue 2",
            "Analogue 3",
            "Analogue 4",
            "Mix A",
            "Mix B",
        ),
        # Analogue outputs:
        scarlett.set_analogue_outputs(
            # Analogue output 0+1 = speaker
            # Analogue output 2+3 = headphones
            "Mix A",
            "Mix B",
            "Mix C",
            "Mix D",
        ),
        scarlett.set_mix(
            # Mixer Inputs:
            [
                "Analogue 1",
                "Analogue 2",
                "Analogue 3",
                "Analogue 4",
                "PCM 1",
                "PCM 2",
                "PCM 3",
                "PCM 4",
            ],
            [100, 0, 100, 0, 0, 0],
            [0, 100, 0, 100, 0, 0],
            [100, 0, 100, 0, 0, 0],
            [0, 100, 0, 100, 0, 0],
            [100, 0, 100, 0, 0, 0],
            [0, 100, 0, 100, 0, 0],
            [100, 0, 100, 0, 0, 0],
            [0, 100, 0, 100, 0, 0],
        ),
    ).set(True)

    def conf() -> Dict[str, ConnectionTrackProtocol]:
        tracks: Dict[str, ConnectionTrackProtocol] = {}
        tracks["Q"] = scarlett.switch_mix_stereo("AB", 12)
        tracks["W"] = scarlett.switch_mix_stereo("AB", 34)
        tracks["E"] = scarlett.switch_mix_stereo("AB", 56)
        tracks["R"] = scarlett.switch_mix_stereo("AB", 78)
        tracks["A"] = scarlett.switch_mix_stereo("CD", 12)
        tracks["S"] = scarlett.switch_mix_stereo("CD", 34)
        tracks["D"] = scarlett.switch_mix_stereo("CD", 56)
        tracks["F"] = scarlett.switch_mix_stereo("CD", 78)
        return tracks

    return conf


if __name__ == "__main__":
    main()
