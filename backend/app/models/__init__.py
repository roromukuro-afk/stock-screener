# Import additional model modules so Base.metadata sees every table during init_db/ensure_schema.
from . import research_forecast  # noqa: F401
