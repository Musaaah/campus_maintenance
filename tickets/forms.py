"""Forms for the tickets app: submit request, assign technician, update status."""

from typing import ClassVar

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import MaintenanceTicket

User = get_user_model()
Status = MaintenanceTicket.Status

# Name of the Django auth Group whose members can be assigned tickets.
TECHNICIAN_GROUP = "Technician"
# Statuses a technician may set (the first two are set by the system/admin).
TECHNICIAN_STATUSES = (Status.IN_PROGRESS, Status.RESOLVED)


class StyledFormMixin:
    """Adds CSS classes to every widget (Bootstrap-style; change to suit)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            css = "form-select" if isinstance(widget, forms.Select) else "form-control"
            widget.attrs["class"] = f"{widget.attrs.get('class', '')} {css}".strip()


class TechnicianChoiceField(forms.ModelChoiceField):
    """Shows a technician's full name, falling back to their username."""

    def label_from_instance(self, user):
        return user.get_full_name() or user.get_username()


class TicketSubmitForm(StyledFormMixin, forms.ModelForm):
    """Used by students and staff to report an issue.

    The view must set the owner: ticket = form.save(commit=False);
    ticket.created_by = request.user; ticket.save().
    """

    class Meta:
        model = MaintenanceTicket
        fields = ("title", "category", "location", "priority", "description")
        widgets: ClassVar[dict] = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. Leaking tap in Block A"}),
            "location": forms.TextInput(attrs={"placeholder": "Building and room"}),
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if len(title) < 5:
            raise ValidationError("Please give a title of at least 5 characters.")
        return title

    def clean_location(self):
        location = self.cleaned_data["location"].strip()
        if not location:
            raise ValidationError("Please say where the problem is.")
        return location

    def clean_description(self):
        description = self.cleaned_data["description"].strip()
        if len(description) < 15:
            raise ValidationError("Please describe the problem in at least 15 characters.")
        return description


class TicketAssignForm(StyledFormMixin, forms.ModelForm):
    """Used by admins to assign (or reassign) a technician."""

    assigned_to = TechnicianChoiceField(
        queryset=User.objects.none(),
        empty_label="Select a technician",
        label="Technician",
    )

    class Meta:
        model = MaintenanceTicket
        fields: ClassVar[tuple[str, ...]] = ("assigned_to",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(
            groups__name=TECHNICIAN_GROUP, is_active=True
        ).order_by("first_name", "last_name", "username")

    def clean(self):
        cleaned_data = super().clean()
        if self.instance.status == Status.RESOLVED:
            raise ValidationError("Resolved tickets cannot be reassigned.")
        return cleaned_data

    def save(self, commit=True):
        ticket = super().save(commit=False)
        # Only move a new ticket to "Assigned"; reassigning keeps the current status.
        if ticket.status == Status.PENDING:
            ticket.status = Status.ASSIGNED
        if commit:
            ticket.save()
        return ticket


class TicketStatusUpdateForm(StyledFormMixin, forms.ModelForm):
    """Used by the assigned technician (or an admin) to record progress."""

    class Meta:
        model = MaintenanceTicket
        fields: ClassVar[tuple[str, ...]] = ("status",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        status_field = self.fields["status"]
        status_field.choices = [
            (value, label)
            for value, label in status_field.choices
            if value in TECHNICIAN_STATUSES
        ]

    def clean_status(self):
        # The instance still holds the old values here, so this is the current state.
        if not self.instance.assigned_to_id:
            raise ValidationError("Assign a technician before updating progress.")
        if self.instance.status == Status.RESOLVED:
            raise ValidationError("This ticket is already resolved.")
        return self.cleaned_data["status"]


class SignUpForm(StyledFormMixin, UserCreationForm):
    """Self-service registration for students and staff.

    New accounts are always plain requesters. Technician and admin roles are only
    ever granted by an administrator in the Django admin site.

    Optional setting: SIGNUP_EMAIL_DOMAINS = ["example.ac.ke"] restricts signup to
    those email domains. Leave it unset to allow any email address.
    """

    first_name = forms.CharField(max_length=150, label="First name")
    last_name = forms.CharField(max_length=150, label="Last name")
    email = forms.EmailField(label="Email address")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        allowed = getattr(settings, "SIGNUP_EMAIL_DOMAINS", None)
        if allowed:
            domains = {domain.lower() for domain in allowed}
            if email.rsplit("@", 1)[-1] not in domains:
                shown = ", ".join(f"@{domain}" for domain in allowed)
                raise ValidationError(f"Please use your institution email address ({shown}).")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email address already exists.")
        return email