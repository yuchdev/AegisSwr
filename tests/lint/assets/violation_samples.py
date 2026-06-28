"""
Violation Samples for Linting.
"""

def x001_violation():
    try:
        pass
    except: # X001
        pass

def x002_violation():
    try:
        pass
    except Exception: # X002
        pass

class Settings:
    def set(self, key, value): # X003
        pass

def x004_violation():
    try:
        raise ValueError()
    except ValueError:
        pass # X004

def x005_violation():
    pass # X005 - missing docstring

def x006_violation():
    import os # X006 - top-level import in a function (should be top-level in module)

def x007_violation(x): # X007 - missing return type annotation
    return x

def x008_violation() -> None: # X008 - None return annotation
    return

def x009_violation(logger):
    logger.info("Log %s", "message") # X009

def x010_violation():
    try:
        import non_existent # X010
    except ImportError:
        non_existent = None

def x011_violation(a: int | None): # X011
    return a
