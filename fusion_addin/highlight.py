import adsk.core
import adsk.fusion

from .log import get_logger

log = get_logger()


def highlight(app, tokens):
    """Select the entities behind the given entityTokens (Design.findEntityByToken -> list).
    Returns the number selected."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        return 0
    sels = app.userInterface.activeSelections
    sels.clear()
    n = 0
    for tok in tokens:
        if not tok:
            continue
        found = design.findEntityByToken(tok)
        if not found:
            log.warning("entity token resolved to nothing (model changed since analysis?): %.60s", tok)
        for ent in found or []:
            if sels.add(ent):
                n += 1
    return n
