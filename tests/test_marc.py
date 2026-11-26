"""Tests for the MARC21 conversion (bibra.marc)."""

from pymarc import Field

from bibra.marc import _build_pymarc_record, to_marc
from bibra.types import MarcField, MarcRecord, PublicationMetadata


def _tags(record: MarcRecord) -> list[str]:
    """Return the list of MARC tags in a record."""
    return [next(iter(entry)) for entry in record.fields]


def _fields_with_tag(tag: str, record: MarcRecord) -> list[MarcField]:
    """Return all MarcField values with the given tag (skips control fields)."""
    fields: list[MarcField] = []
    for entry in record.fields:
        if tag not in entry:
            continue
        value = entry[tag]
        if isinstance(value, MarcField):
            fields.append(value)
    return fields


def _subfields(tag: str, record: MarcRecord) -> list[list[dict[str, str]]]:
    """Return the subfields of all fields with the given tag."""
    return [field.subfields for field in _fields_with_tag(tag, record)]


def _indicator(tag: str, record: MarcRecord) -> list[tuple[str | None, str | None]]:
    """Return (ind1, ind2) pairs for all fields with the given tag."""
    return [(field.ind1, field.ind2) for field in _fields_with_tag(tag, record)]


def test_to_marc_full_metadata():
    """A fully populated metadata object maps to all expected MARC tags."""
    metadata = PublicationMetadata(
        language="en",
        title="A Title",
        alt_title="An Alt Title",
        creator=["Smith, John", "Doe, Jane"],
        year="2023",
        publisher=["Springer"],
        doi="10.1234/example.doi.12345",
        e_isbn=["978-0-123456-78-9"],
        p_isbn=["978-0-987654-32-1"],
        e_issn="1234-5678",
        p_issn="2345-6789",
        type_coar="article",
    )

    record = to_marc(metadata)
    # Fields are emitted in ascending tag order.
    assert _tags(record) == [
        "020",
        "020",
        "022",
        "022",
        "024",
        "041",
        "245",
        "264",
        "655",
    ]
    assert _subfields("020", record) == [
        [{"a": "978-0-987654-32-1"}],
        [{"a": "978-0-123456-78-9"}],
    ]
    assert _indicator("020", record) == [(" ", " "), (" ", " ")]
    assert _subfields("022", record) == [
        [{"a": "2345-6789"}],
        [{"a": "1234-5678"}],
    ]
    assert _indicator("022", record) == [(" ", " "), (" ", " ")]
    assert _subfields("024", record) == [
        [{"a": "10.1234/example.doi.12345"}, {"2": "doi"}]
    ]
    assert _indicator("024", record) == [("7", " ")]
    assert _subfields("041", record) == [[{"a": "en"}, {"2": "bcp47"}]]
    assert _indicator("041", record) == [(" ", "7")]
    assert _subfields("245", record) == [
        [
            {"a": "A Title"},
            {"b": "An Alt Title"},
            {"c": "Smith, John ; Doe, Jane"},
        ]
    ]
    assert _indicator("245", record) == [("0", "0")]
    assert _subfields("264", record) == [
        [
            {"a": "[Place of publication not identified] :"},
            {"b": "Springer"},
            {"c": "2023"},
        ]
    ]
    assert _indicator("264", record) == [(" ", "1")]
    assert _subfields("655", record) == [[{"a": "article"}, {"2": "coar"}]]
    assert _indicator("655", record) == [(" ", "7")]


def test_to_marc_empty_metadata():
    """An empty metadata object produces a record with no fields."""
    record = to_marc(PublicationMetadata())
    assert isinstance(record, MarcRecord)
    assert record.fields == []


def test_to_marc_partial_metadata():
    """Only non-empty source values produce MARC fields."""
    metadata = PublicationMetadata(title="A Title", creator=["Solo, A"])
    record = to_marc(metadata)
    assert _tags(record) == ["245"]
    assert _subfields("245", record) == [[{"a": "A Title"}, {"c": "Solo, A"}]]


def test_to_marc_single_creator():
    """A single creator maps to 245 subfield c only."""
    record = to_marc(PublicationMetadata(creator=["Smith, John"]))
    assert _tags(record) == ["245"]
    assert _subfields("245", record) == [[{"c": "Smith, John"}]]


def test_to_marc_multiple_creators():
    """All creators are joined into a single 245 subfield c."""
    record = to_marc(PublicationMetadata(creator=["A, One", "B, Two", "C, Three"]))
    assert _tags(record) == ["245"]
    assert _subfields("245", record) == [[{"c": "A, One ; B, Two ; C, Three"}]]


def test_to_marc_publisher_without_year():
    """Publishers without a year produce a 264 with subfields b and a."""
    record = to_marc(PublicationMetadata(publisher=["Springer", "ACM"]))
    assert _subfields("264", record) == [
        [
            {"a": "[Place of publication not identified] :"},
            {"b": "Springer"},
            {"b": "ACM"},
        ]
    ]
    assert _indicator("264", record) == [(" ", "1")]


def test_to_marc_year_without_publisher():
    """A year without publisher fills in placeholder subfields b and a."""
    record = to_marc(PublicationMetadata(year="2023"))
    assert _subfields("264", record) == [
        [
            {"a": "[Place of publication not identified] :"},
            {"b": "[publisher not identified],"},
            {"c": "2023"},
        ]
    ]
    assert _indicator("264", record) == [(" ", "1")]


def test_to_marc_multiple_isbns():
    """Each ISBN gets its own 020 field with subfield a."""
    record = to_marc(
        PublicationMetadata(p_isbn=["1111-1", "1111-2"], e_isbn=["2222-1", "2222-2"])
    )
    assert _tags(record) == ["020", "020", "020", "020"]
    assert _subfields("020", record) == [
        [{"a": "1111-1"}],
        [{"a": "1111-2"}],
        [{"a": "2222-1"}],
        [{"a": "2222-2"}],
    ]


def test_to_marc_skips_empty_strings():
    """Empty-string values are skipped rather than emitted."""
    record = to_marc(
        PublicationMetadata(
            title="",
            creator=["", "Valid, Name"],
            publisher=[""],
            year="",
            doi="",
        )
    )
    # Empty title, publisher, year, and doi are skipped; only the valid creator
    # ends up in a 245 field.
    assert _tags(record) == ["245"]
    assert _subfields("245", record) == [[{"c": "Valid, Name"}]]


def test_to_marc_data_fields_are_marc_field_instances():
    """Every data field value is a MarcField with the expected attribute types."""
    record = to_marc(PublicationMetadata(title="A Title"))
    for entry in record.fields:
        assert len(entry) == 1
        field = next(iter(entry.values()))
        assert isinstance(field, MarcField)
        assert isinstance(field.subfields, list)
        for subfield in field.subfields:
            assert len(subfield) == 1
            assert isinstance(next(iter(subfield.keys())), str)
            assert isinstance(next(iter(subfield.values())), str)


def test_to_marc_control_fields_stay_strings():
    """Control fields from pymarc stay plain strings in the record model."""
    metadata = PublicationMetadata(title="A Title")
    pymarc_record = _build_pymarc_record(metadata)
    pymarc_record.add_field(Field(tag="001", data="12345"))

    record = MarcRecord.model_validate({"fields": pymarc_record.as_dict()["fields"]})
    control_001 = next(entry["001"] for entry in record.fields if "001" in entry)
    assert control_001 == "12345"
    assert isinstance(control_001, str)
    marc_245 = next(entry["245"] for entry in record.fields if "245" in entry)
    assert isinstance(marc_245, MarcField)
