from django.contrib import admin
from django.urls import path
from api_tester import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('session/get/', views.get_session, name='get_session'),
    path('session/clear/', views.clear_session, name='clear_session'),
    path('pay/b2b/', views.b2b_payment, name='b2b_payment'),
    path('pay/b2c/', views.b2c_payment, name='b2c_payment'),
    path('pay/c2b/', views.c2b_payment, name='c2b_payment'),
    path('pay/reversal/', views.reversal, name='reversal'),
    path('pay/status/', views.query_status, name='query_status'),
    path('logs/clear/', views.clear_logs, name='clear_logs'),

    # Betting App routes
    path('bet/deposit/', views.betting_deposit, name='bet_deposit'),
    path('bet/withdraw/', views.betting_withdraw, name='bet_withdraw'),
]
