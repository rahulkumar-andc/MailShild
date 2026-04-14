from django.contrib import admin
from django.urls import path, include
from analyzer.api_views import receive_wa_message

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/wa-message/', receive_wa_message, name='wa-message-api'),
    path('', include('dashboard.urls')),
]

