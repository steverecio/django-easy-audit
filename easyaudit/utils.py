import datetime as dt

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import NOT_PROVIDED, DateTimeField
from django.utils import timezone
from django.utils.encoding import smart_str


def get_field_value(obj, field):
    """Get the value of a given model instance field.

    :param obj: The model instance.
    :type obj: Model
    :param field: The field you want to find the value of.
    :type field: Any
    :return: The value of the field as a string.
    :rtype: str
    """
    if isinstance(field, DateTimeField):
        # DateTimeFields are timezone-aware, so we need to convert the field
        # to its naive form before we can accurately compare them for changes.
        try:
            value = field.to_python(getattr(obj, field.name, None))
            if value is not None and settings.USE_TZ and not timezone.is_naive(value):
                value = timezone.make_naive(value, timezone=dt.timezone.utc)
        except ObjectDoesNotExist:
            value = field.default if field.default is not NOT_PROVIDED else None
    else:
        try:
            value = smart_str(getattr(obj, field.name, None))
        except ObjectDoesNotExist:
            value = field.default if field.default is not NOT_PROVIDED else None

    return value


def model_delta(old_model, new_model):
    """Provide delta/difference between two models.

    :param old: The old state of the model instance.
    :type old: Model
    :param new: The new state of the model instance.
    :type new: Model
    :return: A dictionary with the names of the changed fields as keys and a
             two tuple of the old and new field values
             as value.
    :rtype: dict
    """
    delta = {}
    fields = new_model._meta.fields
    for field in fields:
        old_value = get_field_value(old_model, field)
        new_value = get_field_value(new_model, field)
        if old_value != new_value:
            delta[field.name] = [smart_str(old_value), smart_str(new_value)]

    if len(delta) == 0:
        delta = None

    return delta


def get_m2m_field_name(model, instance):
    """Find M2M field name on instance.

    Called from m2m_changed signal
    :param model: m2m_changed signal model.
    :type model: Model
    :param instance:m2m_changed signal instance.
    :type new: Model
    :return: ManyToManyField name of instance related to model.
    :rtype: str
    """
    for x in model._meta.related_objects:
        if x.related_model().__class__ == instance.__class__:
            return x.remote_field.name
    return None


def fit_to_field(model, field_name, value):
    """Cut a string to the max_length of a model's field, keeping its start.

    Several logged values come from the client (the path, the method, a failed
    login's username). One longer than its column fails the insert, and the event
    is lost; a cut value keeps the event.
    """
    max_length = model._meta.get_field(field_name).max_length
    if not isinstance(value, str) or max_length is None:
        return value
    return value[:max_length]


def fit_forwarded_chain(model, field_name, value):
    """Fit an address, or a comma-separated chain of them, into a model's field.

    Proxies append to X-Forwarded-For, so the entries a deployment can trust are at
    the right end and the left end is whatever the client sent. Whole entries are
    dropped from the left until the chain fits; a single entry still too long keeps
    its last max_length characters.
    """
    max_length = model._meta.get_field(field_name).max_length
    if not isinstance(value, str) or max_length is None or len(value) <= max_length:
        return value

    entries = [entry.strip() for entry in value.split(",")]
    while len(entries) > 1 and len(", ".join(entries)) > max_length:
        entries.pop(0)
    return ", ".join(entries)[-max_length:]


def should_propagate_exceptions():
    """Whether Django Easy Audit should propagate signal handler exceptions.

    :rtype: bool
    """
    return getattr(settings, "DJANGO_EASY_AUDIT_PROPAGATE_EXCEPTIONS", False)
