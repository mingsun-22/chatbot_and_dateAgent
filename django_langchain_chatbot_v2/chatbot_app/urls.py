from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_view, name='chat'),
    path('api/chat/', views.api_chat, name='api_chat'),
    path('api/health/', views.health_check, name='health_check'),
    path('sessions/', views.sessions_view, name='sessions'),
]
