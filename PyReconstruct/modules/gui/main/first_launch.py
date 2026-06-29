"""First-launch / startup helpers.

Pure logic kept deliberately free of Qt *widgets* so it can be unit-tested
headlessly. The GUI shell that calls this lives in ``main_window``.
"""

from PyReconstruct.modules.datatypes.default_settings import get_username


# --- username ----------------------------------------------------------------
def resolve_username(settings, series=None, default_factory=get_username):
    """Resolve the tracking username silently -- never prompts.

    Uses a name already saved on this machine; otherwise falls back to the OS
    login (the documented default) and persists it so it is stable across runs.
    Sets ``series.user`` when a series is given so trace-history attribution
    still has a name.

        Params:
            settings: a QSettings-like object (``value``/``setValue``).
            series: the open series whose ``user`` should be set (optional).
            default_factory: callable returning the fallback name.

        Returns:
            (str) the resolved username.
    """
    name = settings.value("username")
    if not (isinstance(name, str) and name.strip()):
        name = (default_factory() or "").strip() or "default"
        settings.setValue("username", name)
    if series is not None:
        series.user = name
    return name
