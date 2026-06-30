import logging
import time


api_logger = logging.getLogger('jamii_aide.api')


class ApiRequestLoggingMiddleware:
    """Log API request/response metadata for quick integration debugging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - start) * 1000

        user_id = getattr(request.user, 'id', None) if hasattr(request, 'user') else None
        api_logger.info(
            'API %s %s status=%s duration_ms=%.2f user_id=%s',
            request.method,
            request.get_full_path(),
            getattr(response, 'status_code', None),
            duration_ms,
            user_id,
        )
        return response