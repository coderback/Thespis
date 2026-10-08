"""The local runtime: models that run on the player's own machine, so Thespis plays offline.

registry: what can be fetched, pinned by checksum. download: resumable, checked fetching. hardware: what this machine can
run. local: starting llama.cpp's server on a model, tied to the life of the process that started it.
"""
