from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def register_validation_handler(app):
    """
        Register a global handler for Pydantic validation errors that returns concise errors and status code 400.

        This function registers a custom exception handler for RequestValidationError exceptions
        in a FastAPI application. When a validation error occurs, the handler transforms the
        default Pydantic validation errors into a simplified, more readable format before
        returning them to the client with a 400 Bad Request status code.

        Args:
            app: The FastAPI application instance to which the exception handler will be registered.

        Returns:
            None: This function does not return a value. It registers the exception handler as a side effect.
    """

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """
            Handle RequestValidationError exceptions and return simplified error responses.

            This handler processes Pydantic validation errors and transforms them into a
            simplified format containing the error type, location, message, and validation context.

            Args:
                request (Request): The incoming HTTP request that triggered the validation error.
                exc (RequestValidationError): The validation error exception containing details
                                             about all validation failures.

            Returns:
                JSONResponse: A JSON response with status code 400 containing a list of simplified
                             error details in the format:
                             {
                                 "details": [
                                     {
                                         "type": str,
                                         "location": str,
                                         "message": str,
                                         "validation": dict or None,
                                         "input": any
                                     }
                                 ]
                             }
        """
        simplified_errors = []
        for err in exc.errors():
            error_payload = {
                'type': err.get('type'),
                'location': ".".join(str(i) for i in err.get("loc", [])),
                'message': err.get('msg'),
                'validation': err.get('ctx'),
                'input': err.get('input')
            }

            simplified_errors.append(error_payload)

        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"details": simplified_errors}
        )
