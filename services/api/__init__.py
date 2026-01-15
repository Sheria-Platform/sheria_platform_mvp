from fastapi.openapi.utils import get_openapi


def custom_openapi(_app):
    """
    Generate a custom OpenAPI schema with JWT Bearer authentication configuration.

    This function creates or retrieves a cached OpenAPI schema for the Sheria Platform API.
    If the schema already exists, it returns the cached version. Otherwise, it generates
    a new schema with custom security configurations including JWT Bearer authentication.

    Args:
        _app (FastAPI): The FastAPI application instance for which to generate the OpenAPI
                      schema. The app must have a routes attribute containing all registered
                      API routes.

    Returns:
        dict: The OpenAPI schema dictionary containing API documentation, security schemes,
             and all route definitions. The schema includes BearerAuth security configuration
             with JWT format for authentication.
    """
    if _app.openapi_schema:
        return _app.openapi_schema

    openapi_schema = get_openapi(
        title="Sheria Platform API",
        description="API for managing Sheria Platform",
        contact={
            "name": "Sheria Platform Team"
        },
        version="1.0.0",
        routes=_app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "Bearer",
            "bearerFormat": "JWT"
        }
    }
    openapi_schema["security"] = [{"BearerAuth": []}]
    _app.openapi_schema = openapi_schema

    return _app.openapi_schema
