# flake8: noqa: N999

from django.urls import path

from . import views

app_name = "tickets"

urlpatterns = [
    path("", views.home, name="home"),
    path("signup/", views.signup, name="signup"),
    path("tickets/", views.ticket_list, name="ticket_list"),
    path("tickets/new/", views.ticket_create, name="ticket_create"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("tickets/<int:pk>/assign/", views.ticket_assign, name="ticket_assign"),
    path("tickets/<int:pk>/status/", views.ticket_update_status, name="ticket_update_status"),
    path("dashboard/", views.dashboard, name="dashboard"),
]