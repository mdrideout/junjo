from typing import Optional


class JunjoApp:
    _instance: Optional["JunjoApp"] = None
    _app_name: str = ""  # Class-level attribute for app_name

    def __new__(cls, app_name: str | None = None):
        if cls._instance is None:
            if app_name is None:
                raise ValueError("app_name must be provided on first initialization")
            cls._instance = super().__new__(cls)
            cls._instance._app_name = app_name.strip()  # Initialize directly
        elif app_name is not None and app_name.strip() != cls._instance._app_name:
            print("Warning: app_name cannot be changed once set")
        return cls._instance

    def __init__(self, app_name: str | None = None):
        # The constructor will always be called.
        # Even though this does nothing, it is conventional
        # to include it.
        pass

    @property  # Make app_name a read-only property
    def app_name(self) -> str:
        return self._app_name
