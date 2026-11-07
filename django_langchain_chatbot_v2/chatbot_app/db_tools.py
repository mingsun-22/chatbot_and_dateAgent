from .models import Contact

def save_contact(source_text: str, contact_type: str, contact_value: str):
    Contact.objects.create(
        source_text=source_text,
        contact_type=contact_type,
        contact_value=contact_value
    )