"""
Custom pagination classes for optimized API responses.
Create this file in your project root or in a common app.
"""
from rest_framework.pagination import PageNumberPagination, CursorPagination, LimitOffsetPagination
from rest_framework.response import Response
from collections import OrderedDict


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination with page size control.
    Used for most list endpoints.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    
    def get_paginated_response(self, data):
        """Enhanced response with additional metadata"""
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('total_pages', self.page.paginator.num_pages),
            ('current_page', self.page.number),
            ('page_size', self.get_page_size(self.request)),
            ('results', data)
        ]))


class LargeResultsSetPagination(PageNumberPagination):
    """
    Pagination for endpoints with large datasets.
    Used for admin/bulk operations.
    """
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 500


class SmallResultsSetPagination(PageNumberPagination):
    """
    Pagination for endpoints with small, detailed responses.
    Used for detailed product listings, reviews, etc.
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50


class ProductCursorPagination(CursorPagination):
    """
    Cursor-based pagination for products.
    More efficient for large datasets with frequent updates.
    Prevents issues with items being skipped or duplicated.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    ordering = '-created_at'  # Must match an indexed field
    cursor_query_param = 'cursor'
    

class OptimizedLimitOffsetPagination(LimitOffsetPagination):
    """
    Limit/Offset pagination with constraints.
    Useful for infinite scroll implementations.
    """
    default_limit = 20
    max_limit = 100
    limit_query_param = 'limit'
    offset_query_param = 'offset'
    
    def get_paginated_response(self, data):
        """Enhanced response with calculation optimization"""
        return Response(OrderedDict([
            ('count', self.count),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('limit', self.limit),
            ('offset', self.offset),
            ('results', data)
        ]))


class NoPagination(PageNumberPagination):
    """
    Disable pagination for specific endpoints.
    Use sparingly and only for guaranteed small datasets.
    """
    page_size = None
    max_page_size = None