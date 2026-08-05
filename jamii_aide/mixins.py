from django.conf import settings


class ApiDebugMixin:
    """Attach serializer metadata for non-production response debug headers."""

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if settings.DEBUG and getattr(self, 'request', None) is not None:
            self.request._api_debug = getattr(self.request, '_api_debug', {})
            self.request._api_debug['serializer'] = serializer.__class__.__name__
        return serializer
