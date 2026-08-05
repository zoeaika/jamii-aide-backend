import logging
import time
import uuid

from django.conf import settings


api_logger = logging.getLogger('jamii_aide.api')


class ApiRequestLoggingMiddleware:
    """Log API request/response metadata for quick integration debugging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith('/api/'):
            return self.get_response(request)

        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        request.request_id = request_id

        start = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - start) * 1000

        response['X-Request-ID'] = request_id

        user_id = getattr(request.user, 'id', None) if hasattr(request, 'user') else None
        api_logger.info(
            'API %s %s status=%s duration_ms=%.2f user_id=%s request_id=%s',
            request.method,
            request.get_full_path(),
            getattr(response, 'status_code', None),
            duration_ms,
            user_id,
            request_id,
        )

        if settings.DEBUG:
            self._attach_debug_headers(request, response)

        return response

    def _attach_debug_headers(self, request, response):
        response['X-API-Debug'] = 'enabled'
        response['X-API-Endpoint-Version'] = 'v1'

        debug_meta = getattr(request, '_api_debug', {})
        serializer_name = debug_meta.get('serializer')
        if serializer_name:
            response['X-API-Serializer'] = serializer_name

        response_data = getattr(response, 'data', None)
        if isinstance(response_data, dict) and 'count' in response_data and 'results' in response_data:
            page_size = settings.REST_FRAMEWORK.get('PAGE_SIZE', 20)
            response['X-API-Pagination'] = 'paginated'
            response['X-API-Page'] = request.GET.get('page', '1')
            response['X-API-Page-Size'] = str(page_size)
            response['X-API-Count'] = str(response_data.get('count', ''))
        elif isinstance(response_data, list):
            response['X-API-Pagination'] = 'array'
        else:
            response['X-API-Pagination'] = 'single'
