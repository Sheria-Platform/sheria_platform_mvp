from typing import Any, List, Optional

from fastapi import Query
from pydantic import BaseModel


class Pagination(BaseModel):
    """
    A model representing pagination parameters for API requests.

    This class encapsulates the essential parameters needed to paginate through
    a collection of items, including the page number, items per page, and sort order.

    Attributes:
        per_page (int): The number of items to display per page.
        page (int): The current page number being requested.
        ordering (str): The sort order for the results, either 'asc' for ascending
            or 'desc' for descending.
    """
    per_page: int
    page: int
    ordering: str


def pagination_params(
        page: int = Query(ge=1, required=False, default=1),
        per_page: int = Query(ge=1, le=100, required=False, default=10),
        ordering: str = Query(pattern='^(asc|desc)$', default='desc', required=False)):
    """
    Create pagination parameters for API endpoints.

    This function serves as a FastAPI dependency that extracts and validates
    pagination parameters from query strings.

    Args:
        page (int, optional): The page number to retrieve. Must be greater than or equal to 1.
            Defaults to 1.
        per_page (int, optional): The number of items per page. Must be between 1 and 100.
            Defaults to 10.
        ordering (str, optional): The sort order for results. Must be either 'asc' for ascending
            or 'desc' for descending. Defaults to 'desc'.

    Returns:
        Pagination: A Pagination object containing the validated page, per_page, and ordering values.
    """
    return Pagination(page=page, per_page=per_page, ordering=ordering)


class PaginatedResponse(BaseModel):
    """
    A response model for paginated API results.

    This class represents the structure of a paginated response, containing
    metadata about the pagination state and the actual items for the current page.

    Attributes:
        count (int): The total number of items across all pages.
        page (int): The current page number being returned.
        per_page (int): The number of items per page.
        next_page (Optional[str]): The URL or identifier for the next page of results.
            None if there is no next page.
        previous_page (Optional[str]): The URL or identifier for the previous page of results.
            None if there is no previous page.
        has_next (Optional[bool]): A boolean flag indicating whether a next page exists.
            Defaults to False.
        has_previous (Optional[bool]): A boolean flag indicating whether a previous page exists.
            Defaults to False.
        data (List[Any]): The list of items for the current page. Can contain any type of object.
    """
    count: int
    page: int
    per_page: int
    next_page: Optional[str] = None
    previous_page: Optional[str] = None
    has_next: Optional[bool] = False
    has_previous: Optional[bool] = False
    data: List[Any]
