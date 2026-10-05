from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, When
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import (
    TECHNICIAN_GROUP,
    SignUpForm,
    TicketAssignForm,
    TicketStatusUpdateForm,
    TicketSubmitForm,
)
from .models import MaintenanceTicket
from .permissions import (
    admin_required,
    can_update_status,
    is_admin,
    is_technician,
    visible_tickets,
)

Status = MaintenanceTicket.Status
Priority = MaintenanceTicket.Priority
User = get_user_model()
PAGE_SIZE = 10


def _flash_form_errors(request, form):
    for errors in form.errors.values():
        for error in errors:
            messages.error(request, error)


@login_required
def home(request):
    if is_admin(request.user):
        return redirect("tickets:dashboard")
    return redirect("tickets:ticket_list")


def signup(request):
    if request.user.is_authenticated:
        return redirect("tickets:home")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()  # a plain requester: not staff, not a technician
            login(request, user)
            messages.success(request, "Welcome! Your account is ready. You can now report a maintenance issue.")
            return redirect("tickets:home")
    else:
        form = SignUpForm()
    return render(request, "registration/signup.html", {"form": form})


@login_required
def ticket_create(request):
    if request.method == "POST":
        form = TicketSubmitForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.created_by = request.user  # never taken from the form
            ticket.save()
            messages.success(request, f"Request #{ticket.pk} submitted. You can track it here.")
            return redirect("tickets:ticket_detail", pk=ticket.pk)
    else:
        form = TicketSubmitForm()
    return render(request, "tickets/ticket_form.html", {"form": form})


@login_required
def ticket_list(request):
    user = request.user
    tickets = visible_tickets(user)

    status = request.GET.get("status", "")
    category = request.GET.get("category", "")
    query = request.GET.get("q", "").strip()
    if status in Status.values:
        tickets = tickets.filter(status=status)
    if category in MaintenanceTicket.Category.values:
        tickets = tickets.filter(category=category)
    if query:
        tickets = tickets.filter(Q(title__icontains=query) | Q(location__icontains=query))

    if is_admin(user):
        list_title = "All requests"
    elif is_technician(user):
        list_title = "My assigned jobs"
    else:
        list_title = "My requests"

    page_obj = Paginator(tickets, PAGE_SIZE).get_page(request.GET.get("page"))
    context = {
        "page_obj": page_obj,
        "list_title": list_title,
        "status_choices": Status.choices,
        "category_choices": MaintenanceTicket.Category.choices,
        "current_status": status,
        "current_category": category,
        "query": query,
    }
    return render(request, "tickets/ticket_list.html", context)


@login_required
def ticket_detail(request, pk):
    # A ticket the user may not see gives 404, so ticket numbers can't be probed.
    ticket = get_object_or_404(visible_tickets(request.user), pk=pk)
    can_assign = is_admin(request.user) and ticket.status != Status.RESOLVED
    can_update = can_update_status(request.user, ticket)
    context = {
        "ticket": ticket,
        "can_assign": can_assign,
        "can_update": can_update,
        "assign_form": TicketAssignForm(instance=ticket) if can_assign else None,
        "status_form": TicketStatusUpdateForm(instance=ticket) if can_update else None,
    }
    return render(request, "tickets/ticket_detail.html", context)


@admin_required
@require_POST
def ticket_assign(request, pk):
    ticket = get_object_or_404(MaintenanceTicket, pk=pk)
    form = TicketAssignForm(request.POST, instance=ticket)
    if form.is_valid():
        ticket = form.save()
        name = ticket.assigned_to.get_full_name() or ticket.assigned_to.get_username()
        messages.success(request, f"Request #{ticket.pk} assigned to {name}.")
    else:
        _flash_form_errors(request, form)
    return redirect("tickets:ticket_detail", pk=pk)


@login_required
@require_POST
def ticket_update_status(request, pk):
    ticket = get_object_or_404(visible_tickets(request.user), pk=pk)
    # Only an admin or the assigned technician may change progress.
    if not (is_admin(request.user) or ticket.assigned_to_id == request.user.id):
        raise PermissionDenied
    form = TicketStatusUpdateForm(request.POST, instance=ticket)
    if form.is_valid():
        ticket = form.save()
        messages.success(request, f"Request #{ticket.pk} is now {ticket.get_status_display()}.")
    else:
        _flash_form_errors(request, form)
    return redirect("tickets:ticket_detail", pk=pk)


@admin_required
def dashboard(request):
    all_tickets = MaintenanceTicket.objects.all()
    counts = dict(all_tickets.values_list("status").annotate(n=Count("id")))
    status_counts = [
        {"value": value, "label": label, "count": counts.get(value, 0)}
        for value, label in Status.choices
    ]

    priority_rank = Case(
        When(priority=Priority.URGENT, then=0),
        When(priority=Priority.HIGH, then=1),
        When(priority=Priority.MEDIUM, then=2),
        default=3,
        output_field=IntegerField(),
    )
    unassigned = (
        all_tickets.filter(assigned_to__isnull=True)
        .exclude(status=Status.RESOLVED)
        .select_related("created_by")
        .annotate(rank=priority_rank)
        .order_by("rank", "created_at")
    )
    technicians = (
        User.objects.filter(groups__name=TECHNICIAN_GROUP, is_active=True)
        .annotate(
            open_jobs=Count(
                "tickets_assigned",
                filter=~Q(tickets_assigned__status=Status.RESOLVED),
            )
        )
        .order_by("open_jobs", "username")
    )
    context = {
        "total": all_tickets.count(),
        "status_counts": status_counts,
        "unassigned_count": unassigned.count(),
        "unassigned": unassigned[:10],
        "technicians": technicians,
    }
    return render(request, "tickets/dashboard.html", context)