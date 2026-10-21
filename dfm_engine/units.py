"""Unit helpers. The engine's native unit is millimetres."""
MM_PER_IN = 25.4


def in_to_mm(v):
    return None if v is None else v * MM_PER_IN


def mm_to_in(v):
    return None if v is None else v / MM_PER_IN


def fmt_len(mm, both=True):
    """'7.63 mm (0.300 in)' - both units so reports are unambiguous."""
    if mm is None:
        return "n/a"
    return f"{mm:.2f} mm ({mm / MM_PER_IN:.3f} in)" if both else f"{mm:.2f} mm"
