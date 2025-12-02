import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class MonitoringMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000
            
            if hasattr(request.app.state, "monitoring_handler"):
                monitoring = request.app.state.monitoring_handler
                monitoring.log_request(
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    user_agent=request.headers.get("user-agent", ""),
                    ip_address=request.client.host if request.client else ""
                )
            
            return response
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            if hasattr(request.app.state, "monitoring_handler"):
                monitoring = request.app.state.monitoring_handler
                monitoring.log_error(
                    method=request.method,
                    path=request.url.path,
                    error_type=type(e).__name__,
                    error_message=str(e)
                )
            
            raise
