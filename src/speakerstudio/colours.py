"""Verified legacy finish identifiers; unknown codes never imply a colour."""
# Basic codes are factual LegacyDeviceColor enum values recovered with REA.
# Unicorn 0x0431 was read from the user's HUMBOLDT speaker and matched to the
# supplied phone-app screenshot and the official Unicorn packshot.
FINISHES = {
    'boom-3': {
        0x110:'Night black', 0x111:'Forest', 0x112:'Lagoon blue',
        0x113:'Ultraviolet purple', 0x114:'Sunset red', 0x115:'Seashell peach',
        0x11c:'Denim', 0x11d:'Cloud',
    },
    'megaboom-3': {
        0x116:'Night black', 0x117:'Forest', 0x118:'Lagoon blue',
        0x119:'Ultraviolet purple', 0x11a:'Sunset red', 0x11b:'Seashell peach',
        0x11e:'Denim', 0x11f:'Cloud', 0x431:'Unicorn pink',
    },
}


def finish_name(model, code):
    return FINISHES.get(model, {}).get(code, '')
