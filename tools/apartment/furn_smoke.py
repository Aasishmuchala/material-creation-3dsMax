"""Harness smoke test: one stool."""
import kit


def build_stool():
    seat = kit.part(kit.cbox(40, 40, 4, 1.2, 0, 0, 44), "wood_light", 60)
    legs = [kit.part(kit.cyl(1.6, 44, x, y, 0), "metal_black") for x in (-16, 16) for y in (-16, 16)]
    return kit.group("Stool", [seat] + legs)


def preview():
    kit.place(build_stool(), 0, 0)
