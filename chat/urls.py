"""
URL configuration for chat project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import path
from . import views

urlpatterns = [
    path('', views.bridge, name='home'),
    # path('compare', views.compare, name='compare'),
    # path('single', views.single, name='single'),
    path('bridge', views.bridge, name='bridge'),
    path('baseline', views.baseline, name='baseline'),
    
    # Chat endpoints
    path('chat/stream/', views.chat_stream, name='chat_stream'),
    path('chat/baseline_stream/', views.chat_baseline_stream, name='chat_baseline_stream'),
    
    # Session management endpoints
    path('sessions/create/', views.create_session, name='create_session'),
    path('sessions/', views.get_sessions, name='get_sessions'),
    path('sessions/delete/', views.delete_session, name='delete_session'),
    path('sessions/messages/', views.get_session_messages, name='get_session_messages'),
    path('sessions/comparison/', views.get_comparison_session, name='get_comparison_session'),
    
    # Comparison turn management
    path('sessions/start_comparison_turn/', views.start_comparison_turn, name='start_comparison_turn'),

    # Research insights
    path('research-insights/', views.research_insights, name='research_insights'),
]