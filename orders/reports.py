import pandas as pd
from django.db.models import Sum, Count, Avg, Q, F
from django.utils import timezone
from datetime import datetime, timedelta
from .models import Order, OrderItem
import plotly.graph_objects as go
import plotly.express as px
from io import BytesIO
import base64


class OrderReports:
    """God-Level Order Reporting System"""
    
    @staticmethod
    def sales_report(start_date, end_date, group_by='day'):
        """Generate sales report"""
        orders = Order.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )
        
        if group_by == 'day':
            data = orders.annotate(
                date=TruncDate('created_at')
            ).values('date').annotate(
                total_sales=Sum('total'),
                order_count=Count('id'),
                avg_order_value=Avg('total')
            ).order_by('date')
        
        elif group_by == 'month':
            data = orders.annotate(
                month=TruncMonth('created_at')
            ).values('month').annotate(
                total_sales=Sum('total'),
                order_count=Count('id'),
                avg_order_value=Avg('total')
            ).order_by('month')
        
        return list(data)
    
    @staticmethod
    def product_performance_report(start_date, end_date):
        """Generate product performance report"""
        items = OrderItem.objects.filter(
            order__created_at__date__gte=start_date,
            order__created_at__date__lte=end_date
        )
        
        data = items.values(
            'product__name', 'product__sku', 'product__category__name'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum(F('price') * F('quantity')),
            order_count=Count('order', distinct=True),
            avg_price=Avg('price')
        ).order_by('-total_revenue')
        
        return list(data)
    
    @staticmethod
    def customer_analysis_report(start_date, end_date):
        """Generate customer analysis report"""
        orders = Order.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).exclude(customer__isnull=True)
        
        # Customer segmentation
        data = orders.values('customer__user__email').annotate(
            total_orders=Count('id'),
            total_spent=Sum('total'),
            avg_order_value=Avg('total'),
            first_order=Min('created_at'),
            last_order=Max('created_at')
        ).order_by('-total_spent')
        
        # RFM Analysis
        rfm_data = []
        for entry in data:
            recency = (timezone.now().date() - entry['last_order'].date()).days
            frequency = entry['total_orders']
            monetary = entry['total_spent']
            
            rfm_data.append({
                'email': entry['customer__user__email'],
                'recency': recency,
                'frequency': frequency,
                'monetary': monetary,
                'rfm_score': (recency * 0.3) + (frequency * 0.4) + (monetary * 0.3)
            })
        
        return {
            'customer_data': list(data),
            'rfm_analysis': rfm_data
        }
    
    @staticmethod
    def create_sales_chart(start_date, end_date):
        """Create sales chart visualization"""
        data = OrderReports.sales_report(start_date, end_date, 'day')
        
        if not data:
            return None
        
        df = pd.DataFrame(data)
        
        fig = go.Figure()
        
        # Add sales line
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['total_sales'],
            mode='lines+markers',
            name='Sales',
            line=dict(color='royalblue', width=2)
        ))
        
        # Add order count bar
        fig.add_trace(go.Bar(
            x=df['date'],
            y=df['order_count'],
            name='Orders',
            yaxis='y2',
            marker_color='lightblue',
            opacity=0.6
        ))
        
        fig.update_layout(
            title='Sales Trend',
            xaxis_title='Date',
            yaxis_title='Sales ($)',
            yaxis2=dict(
                title='Order Count',
                overlaying='y',
                side='right'
            ),
            hovermode='x unified'
        )
        
        # Convert to base64 for HTML embedding
        buffer = BytesIO()
        fig.write_image(buffer, format='png')
        buffer.seek(0)
        
        return base64.b64encode(buffer.read()).decode()
    
    @staticmethod
    def create_product_performance_chart(start_date, end_date):
        """Create product performance chart"""
        data = OrderReports.product_performance_report(start_date, end_date)
        
        if not data:
            return None
        
        df = pd.DataFrame(data)
        df_top10 = df.nlargest(10, 'total_revenue')
        
        fig = go.Figure(data=[
            go.Bar(
                x=df_top10['product__name'],
                y=df_top10['total_revenue'],
                text=df_top10['total_quantity'],
                textposition='auto',
                marker_color='lightseagreen'
            )
        ])
        
        fig.update_layout(
            title='Top 10 Products by Revenue',
            xaxis_title='Product',
            yaxis_title='Revenue ($)',
            xaxis_tickangle=-45
        )
        
        buffer = BytesIO()
        fig.write_image(buffer, format='png')
        buffer.seek(0)
        
        return base64.b64encode(buffer.read()).decode()
    
    @staticmethod
    def generate_pdf_report(start_date, end_date):
        """Generate comprehensive PDF report"""
        # This would use ReportLab or WeasyPrint to generate PDF
        pass