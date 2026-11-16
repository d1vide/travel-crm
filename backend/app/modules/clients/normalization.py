import re
import unicodedata

import phonenumbers
from pydantic import EmailStr, TypeAdapter

EMAIL = TypeAdapter(EmailStr)


def checked_text(value):
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("Текст содержит недопустимые символы")
        value.encode("utf-8")
    return value


def clean_contact(value):
    checked_text(value)
    return value.strip() or None if isinstance(value, str) else value


def normalize_name(value: str) -> str:
    return unicodedata.normalize("NFKC", " ".join(value.split())).casefold().replace("ё", "е")


def normalize_phone(value: str) -> str:
    try:
        number = phonenumbers.parse(value, "RU")
    except phonenumbers.NumberParseException as error:
        raise ValueError("Введите корректный телефон") from error
    if number.extension or not phonenumbers.is_valid_number(number):
        raise ValueError("Введите корректный телефон без добавочного номера")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def normalize_email(value: str) -> str:
    return str(EMAIL.validate_python(value)).lower()


def search_phone(value: str) -> str | None:
    if not re.fullmatch(r"[\d+().\s-]+", value):
        return None
    digits = phonenumbers.normalize_digits_only(value)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits or None


def contains_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
