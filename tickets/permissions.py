"""Role helpers and access rules for the tickets app.

Roles:
  * admin      - Django users with is_staff or is_superuser
  * technician - members of the "Technician" group
  * requester  - any other logged-in user (students and staff)
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q

from .forms import TECHNICIAN_GROUP
from .models import MaintenanceTicket

Status = MaintenanceTicket.Status


def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def is_technician(user):
    return (
        user.is_authenticated
        and user.groups.filter(name=TECHNICIAN_GROUP).exists()
    )


def visible_tickets(user):
    """Tickets this user is allowed to see. Every list and detail page starts here."""
    tickets = MaintenanceTicket.objects.select_related("created_by", "assigned_to")
    if is_admin(user):
        return tickets
    if is_technician(user):
        return tickets.filter(Q(assigned_to=user) | Q(created_by=user))
    return tickets.filter(created_by=user)


def can_update_status(user, ticket):
    """Only an open, assigned ticket can be progressed - by its technician or an admin."""
    if ticket.assigned_to_id is None or ticket.status == Status.RESOLVED:
        return False
    return is_admin(user) or ticket.assigned_to_id == user.id


def user_passes(check):
    """Decorator: require login, then require check(user) to be true (else 403)."""

    def decorator(view):
        @login_required
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not check(request.user):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


admin_required = user_passes(is_admin)