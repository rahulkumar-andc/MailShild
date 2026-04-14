from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='dashboard-index'),
    path('add-favourite/', views.add_favourite, name='add-favourite'),
    path('remove-favourite/<int:user_id>/', views.remove_favourite, name='remove-favourite'),
    path('api/chat/', views.chat_api, name='chat-api'),
]
