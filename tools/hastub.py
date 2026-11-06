"""Minimal stand-ins so the integration modules import without Home Assistant."""
import abc, sys, types

class _Stub:
    """Callable, attribute-permissive placeholder with a readable repr."""
    def __init__(self, name):
        self._name = name
    def __call__(self, *a, **k):
        return _Stub(self._name + "()")
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Stub(f"{self._name}.{name}")
    def __repr__(self):
        return self._name

class _AnyMeta(abc.ABCMeta):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Stub(f"{cls.__name__}.{name}")
    def __getitem__(cls, item):
        return cls

class _Any(metaclass=_AnyMeta):
    def __init__(self, *a, **k):
        pass

class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = _AnyMeta(name, (_Any,), {})
        setattr(self, name, cls)
        return cls

class _Finder:
    def find_module(self, fullname, path=None):
        return None
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root not in ("homeassistant", "voluptuous", "typing_extensions"):
            return None
        import importlib.machinery
        return importlib.machinery.ModuleSpec(fullname, _Loader(), is_package=True)

class _Loader:
    def create_module(self, spec):
        module = _StubModule(spec.name)
        module.__path__ = []
        return module
    def exec_module(self, module):
        pass

def install():
    sys.meta_path.insert(0, _Finder())
    import importlib
    # Real-enough pieces the integration actually relies on.
    ent = importlib.import_module("homeassistant.helpers.entity")
    class Entity:
        _attr_available = True
        @property
        def extra_state_attributes(self):
            return getattr(self, "_attr_extra_state_attributes", {})
    ent.Entity = Entity
    ent.DeviceInfo = dict

    coord = importlib.import_module("homeassistant.helpers.update_coordinator")
    class DataUpdateCoordinator:
        def __init__(self, *a, **k):
            pass
        def __class_getitem__(cls, item):
            return cls
    class CoordinatorEntity(Entity):
        def __init__(self, coordinator):
            self.coordinator = coordinator
        def __class_getitem__(cls, item):
            return cls
        @property
        def available(self):
            return True
    coord.DataUpdateCoordinator = DataUpdateCoordinator
    coord.CoordinatorEntity = CoordinatorEntity
    coord.UpdateFailed = type("UpdateFailed", (Exception,), {})

    exc = importlib.import_module("homeassistant.exceptions")
    exc.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    exc.ServiceValidationError = type("ServiceValidationError", (exc.HomeAssistantError,), {})

    te = importlib.import_module("typing_extensions")
    import typing
    te.NotRequired = typing.NotRequired
