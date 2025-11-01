from backend.format import price_format_from_lakhs, slugify


def test_price_format():
    assert price_format_from_lakhs(120.0).startswith("₹1.20")
    assert price_format_from_lakhs(75.0).endswith("L")


def test_slugify():
    s = "My Project - Baner, Pune"
    slug = slugify(s)
    assert "my-project" in slug
