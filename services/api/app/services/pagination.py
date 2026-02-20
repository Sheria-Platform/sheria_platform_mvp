from fastapi.requests import Request
from sqlalchemy import Select, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.schema.pagination import Pagination


class Paginator:
    """
    A paginator class for handling database query pagination with SQLAlchemy async sessions.

    This class provides functionality to paginate database query results, generate navigation URLs,
    and format paginated responses with metadata.
    """

    def __init__(self,
                 params: Pagination,
                 db_session: AsyncSession,
                 query: Select,
                 request: Request,
                 schema,
                 **kwargs):
        """
        Initialize the Paginator with pagination parameters and database query.

        Args:
            params (Pagination): Pagination parameters containing page number, items per page, and ordering.
            db_session (AsyncSession): SQLAlchemy async database session for executing queries.
            query (Select): SQLAlchemy Select query to be paginated.
            request (Request): FastAPI Request object used for generating pagination URLs.
            schema: Pydantic schema class for validating and serializing query results.
            **kwargs: Additional keyword arguments for extended functionality.
        """
        param_dict = params.model_dump()
        self.param_dict = param_dict
        self.query = query
        self.kwargs = kwargs
        self.request = request
        self.db_session = db_session
        self.schema = schema
        self.number_of_pages: int = 0
        self.page: int = param_dict.get('page', 1)
        self.per_page: int = param_dict.get('per_page', 10)
        self.limit = self.per_page * self.page
        self.offset = (self.page - 1) * self.per_page
        self.has_next = False
        self.has_previous = False

    def _get_next_page(self):
        """
        Generate the URL for the next page if available.

        Returns:
            str or None: URL string for the next page, or None if no next page exists.
        """
        if self.page >= self.number_of_pages:
            return

        self.has_next = True
        return self._compile_url(self.page + 1)

    def _get_previous_page(self):
        """
        Generate the URL for the previous page if available.

        Returns:
            str or None: URL string for the previous page, or None if no previous page exists.
        """
        if self.page == 1 or self.page > self.number_of_pages + 1:
            return

        self.has_previous = True
        return self._compile_url(self.page - 1)

    def _compile_url(self, page):
        """
        Compile a pagination URL with the specified page number.

        Args:
            page (int): The page number to include in the URL.

        Returns:
            str: Complete URL string with query parameters for the specified page.
        """
        current_params = self.param_dict
        current_params['page'] = page

        url = self.request.url.include_query_params(**current_params)

        return f'{url.path}?{url.query}'

    async def get_response(self):
        """
        Generate the complete paginated response with metadata and items.

        This method orchestrates the pagination process by gathering the total count of items,
        calculating navigation URLs, and retrieving the paginated data. It returns a comprehensive
        dictionary containing all pagination metadata and the actual data items for the current page.

        Returns:
            dict: A dictionary containing pagination metadata and data with the following keys:
                - count (int): Total number of items across all pages matching the query criteria.
                - per_page (int): Number of items displayed per page.
                - page (int): Current page number.
                - next_page (str or None): URL for the next page if available, None otherwise.
                - previous_page (str or None): URL for the previous page if available, None otherwise.
                - has_next (bool): Boolean indicating whether a next page exists.
                - has_previous (bool): Boolean indicating whether a previous page exists.
                - data (list): List of paginated items for the current page, validated against the schema.
        """
        payload = {
            'count': await self._get_total_count(),
            'per_page': self.per_page,
            'page': self.page,
            'next_page': self._get_next_page(),
            'previous_page': self._get_previous_page(),
            'has_next': self.has_next,
            'has_previous': self.has_previous,
            'data': await self._query_data(),
        }
        return payload

    async def _query_data(self):
        """
        Execute the paginated query and return validated items.

        Applies ordering (ascending or descending by 'created_at'), limit, and offset
        to the query, then validates results against the schema.

        Returns:
            list: List of schema-validated items for the current page.
        """
        ordering = self.param_dict.get('ordering')
        if ordering and ordering == 'desc':
            self.query = self.query.order_by(
                desc('created_at')
            )
        else:
            self.query = self.query.order_by(
                'created_at'
            )
        data = await self.db_session.scalars(
            self.query.limit(
                self.limit
            ).offset(
                self.offset
            )
        )

        return [self.schema.model_validate(item) for item in data]

    def _get_number_of_pages(self, count: int):
        """
        Calculate the total number of pages based on item count.

        Args:
            count (int): Total number of items to paginate.

        Returns:
            int: Total number of pages required to display all items.
        """
        rest = count % self.per_page
        quotient = count // self.per_page

        return quotient if not rest else quotient + 1

    async def _get_total_count(self) -> int:
        """
        Get the total count of items matching the query.

        Executes a count query and updates the number_of_pages attribute.

        Returns:
            int: Total number of items matching the query criteria.
        """
        count = await self.db_session.scalar(select(func.count()).select_from(self.query.subquery()))
        self.number_of_pages = self._get_number_of_pages(count)

        return count
