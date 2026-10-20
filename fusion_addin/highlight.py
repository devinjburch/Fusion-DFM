import adsk.core
import adsk.fusion


def highlight(app, tokens):
    """Select the entities behind the given entityTokens. Returns number highlighted."""
    design = adsk.fusion.Design.cast(app.activeProduct)
    if design is None:
        return 0
    sels = app.userInterface.activeSelections
    sels.clear()
    n = 0
    for tok in tokens:
        if not tok:
            continue
        for ent in design.findEntityByToken(tok):
            sels.add(ent)
            n += 1
    return n
