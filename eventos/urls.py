from django.urls import path 
from . import views 
urlpatterns = [ path('health/', views.health_check), ]
urlpatterns = [ path('health/', views.health_check), path('db-test/', views.db_test), ]