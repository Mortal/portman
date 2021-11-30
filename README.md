# portman -- live mixers in the terminal for Pipewire

Implements a framework (portman.py) and a sample application (example.py).

To run the example application: `pw-jack python3 example.py`

The example application picks an arbitrary stereo speaker on your system
and allows you to mute/unmute up to 5 arbitrarily-selected applications playing audio.

The example application is intentionally simplistic;
see orchestra.py and streaming.py for realistic applications
that require special hardware (Scarlett 4i4 and Blue Yeti).

Only tested on a system using Pipewire,
so if you use JACK or Pulseaudio directly, it will probably not work.
