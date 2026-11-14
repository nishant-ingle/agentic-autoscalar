import ssl
import _ssl

# Fix Python 3.14 + gevent monkey-patching recursion in ssl.SSLContext
_props = ["minimum_version", "maximum_version", "options", "_msg_callback", "verify_flags", "verify_mode"]
for _prop in _props:
    if hasattr(_ssl, "_SSLContext") and hasattr(ssl, "SSLContext"):
        _target_prop = getattr(ssl.SSLContext, _prop, None)
        _base_prop = getattr(_ssl._SSLContext, _prop, None)
        if _target_prop and _base_prop and hasattr(_base_prop, "__set__"):
            _base_setter = _base_prop.__set__
            def _make_setter(s):
                return lambda self, value: s(self, value)
            try:
                setattr(ssl.SSLContext, _prop, _target_prop.setter(_make_setter(_base_setter)))
            except Exception:
                pass

import gevent.monkey
gevent.monkey.patch_all()
