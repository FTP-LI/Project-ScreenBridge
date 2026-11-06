"""Decide the next host step from the USB identities that are present.

This does not open a device. Accessory mode must not trigger another handshake.
"""

DEBUG_ID = (0x12D1, 0x5000)
ACCESSORY_IDS = {(0x18D1, 0x2D00), (0x18D1, 0x2D01)}


def classify_present(identities):
    identities = list(identities)
    debug = [item for item in identities if item == DEBUG_ID]
    accessory = [item for item in identities if item in ACCESSORY_IDS]
    if len(accessory) == 1 and not debug:
        return "wait_tablet"
    if len(debug) == 1 and not accessory:
        return "handshake"
    if not debug and not accessory:
        return "idle"
    return "ambiguous"
