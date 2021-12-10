from typing import Dict

import pyscarlett
from portman import (
    ConnectionTrackProtocol,
    MultiConnectionTrack,
    PortMan,
    Push,
    Scarlett,
    Swap,
    TuiConf,
    tuiwrapper,
)


@tuiwrapper
def main(pm: PortMan) -> TuiConf:
    brand_name = "Scarlett"
    device_name = f"{brand_name} 4i4"
    client_name = f"{device_name} USB Pro"
    if client_name not in pm.clients:
        found_brand = [c for c in pm.clients if brand_name in c]
        found_device = [c for c in found_brand if device_name in c]
        if found_device:
            raise SystemExit(
                "Couldn't find %r, " % client_name
                + "but did find %r.\n" % found_device[0]
                + "Maybe you need to set the device to "
                + "'Pro Audio' mode?"
            )
        elif found_brand:
            raise SystemExit(
                "Couldn't find %r, " % client_name
                + "but did find %r, " % found_brand[0]
                + "which is not a supported model for this script."
            )
        else:
            raise SystemExit("Couldn't find %r - " % client_name + "is it connected?")

    pm.set_default_sink(client_name)

    scarlett = Scarlett()

    # PCM inputs:
    # 01+02 Default sink on host

    config = MultiConnectionTrack(
        # PCM outputs:
        scarlett.set_pcm_outputs(
            "Mix C", "Mix D", "Mix A", "Mix B", "Mix E", "Mix F"
        ),
        # Analogue outputs:
        scarlett.set_analogue_outputs(
            # Analogue output 0+1 = sound fx out
            # Analogue output 2+3 = piano out
            "Mix A",
            "Mix B",
            "Mix C",
            "Mix D",
        ),
        scarlett.set_mix(
            # Mixer Inputs:
            [
                # Analogue 1+2 = Piano input
                "Analogue 1",
                "Analogue 2",
                # Analogue 3+4 = Playthrough (to sound fx)
                "Analogue 3",
                "Analogue 4",
                # PCM1+2 = Playback from host (to sound fx)
                "PCM 1",
                "PCM 2",
                "Off",
                "Off",
            ],
            [0, 0, None, 0, 100, 0],
            [0, 0, 0, None, 0, 100],
            [100, 0, 0, 0, None, 0],
            [0, 100, 0, 0, 0, None],
            [None, 0, 0, 0, 100, 0],
            [0, None, 0, 0, 0, 100],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
        ),
    )
    config.set(False)
    config.set(True)

    pyscarlett.dump_channels(scarlett.channels)
    onboard = "Built-in Audio Analog Stereo"
    laptop_speaker = pm.stereo_speaker_ref(onboard)
    mixef = pm.stereo_out_ref(client_name, "45")
    pm.multi_connection_track(mixef, laptop_speaker).set(True)

    def conf() -> Dict[str, ConnectionTrackProtocol]:
        tracks: Dict[str, ConnectionTrackProtocol] = {}

        # Playback to speakers
        tracks["Q"] = scarlett.switch_mix_stereo("AB", 56)
        # Piano to speakers
        tracks["W"] = scarlett.switch_mix_stereo("CD", 12)
        # Playthrough to monitor
        tracks["Z"] = scarlett.switch_mix_stereo("EF", 34)
        return tracks

    return conf


if __name__ == "__main__":
    main()
