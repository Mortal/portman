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

    MultiConnectionTrack(
        # PCM outputs:
        scarlett.set_pcm_outputs(
            "Analogue 1", "Analogue 2", "Analogue 3", "Analogue 4", "Mix E", "Mix F"
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
                # PCM1+2 = Playback from host
                "PCM 1",
                "PCM 2",
                # Analogue 3+4 = Piano input
                "Analogue 3",
                "Analogue 4",
                # Analogue 1+2 = Orchestra monitor
                "Analogue 1",
                "Analogue 2",
                "PCM 3",
                "PCM 4",
            ],
            [None, 0, None, 0, 0, 0],
            [0, None, 0, None, 0, 0],
            [None, 0, None, 0, 0, 0],
            [0, None, 0, None, 0, 0],
            [0, 0, None, 0, 0, 0],
            [0, 0, 0, None, 0, 0],
            [0, 0, 0, 0, 100, 0],
            [0, 0, 0, 0, 0, 100],
        ),
    ).set(True)

    pyscarlett.dump_channels(scarlett.channels)

    def conf() -> Dict[str, ConnectionTrackProtocol]:
        tracks: Dict[str, ConnectionTrackProtocol] = {}

        # Playback to headphones
        tracks["Q"] = scarlett.switch_mix_stereo("CD", 12)
        # Piano to headphones
        tracks["W"] = scarlett.switch_mix_stereo("CD", 34)
        # Orchestra to headphones
        tracks["E"] = scarlett.switch_mix_stereo("CD", 56)
        tracks["X"] = Swap(
            tracks["Q"],
            scarlett.switch_mix_stereo("AB", 12),
            tracks["W"],
            scarlett.switch_mix_stereo("AB", 34),
        )
        tracks["Z"] = Push(
            tracks["Q"],
            scarlett.switch_mix_stereo("AB", 12),
            tracks["W"],
            scarlett.switch_mix_stereo("AB", 34),
        )
        blue = "Blue Microphones Pro"
        if blue in pm.clients and pm.clients[blue]["ports"]:
            micout = pm.stereo_out_ref(blue)
            micin = pm.stereo_speaker_ref(client_name, "23")
            # tracks["Z"] = pm.multi_connection_track(micout, micin)
        return tracks

    return conf


if __name__ == "__main__":
    main()
