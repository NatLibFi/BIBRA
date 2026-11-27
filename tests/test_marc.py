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
        alt_title=["An Alt Title"],
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
    # Fields are emitted in the order the conversion builds them. With two
    # creators there is no 100 field (single creator only) and one 700 field
    # per creator. e_isbn takes precedence in 020, p_isbn goes to 776.
    assert _tags(record) == [
        "020",
        "024",
        "041",
        "245",
        "246",
        "264",
        "490",
        "655",
        "700",
        "700",
        "776",
    ]
    assert _subfields("020", record) == [
        [{"a": "978-0-123456-78-9"}, {"q": "electronic resource"}]
    ]
    assert _indicator("020", record) == [(" ", " ")]
    assert _subfields("024", record) == [
        [{"a": "10.1234/example.doi.12345"}, {"2": "doi"}]
    ]
    assert _indicator("024", record) == [("7", " ")]
    assert _subfields("041", record) == [[{"a": "eng"}]]
    assert _indicator("041", record) == [(" ", " ")]
    assert _subfields("245", record) == [
        [
            {"a": "A Title"},
            {"c": "Smith, John ; Doe, Jane"},
        ]
    ]
    assert _indicator("245", record) == [("0", "0")]
    assert _subfields("246", record) == [[{"a": "An Alt Title"}]]
    assert _indicator("246", record) == [("3", " ")]
    assert _subfields("264", record) == [
        [
            {"a": "[Place of publication not identified] :"},
            {"b": "Springer"},
            {"c": "2023"},
        ]
    ]
    assert _indicator("264", record) == [(" ", "1")]
    assert _subfields("490", record) == [[{"x": "2345-6789"}, {"x": "1234-5678"}]]
    assert _indicator("490", record) == [("0", " ")]
    assert _subfields("655", record) == [[{"a": "article"}, {"2": "coar"}]]
    assert _indicator("655", record) == [(" ", "7")]
    assert _subfields("700", record) == [
        [{"a": "Smith, John"}],
        [{"a": "Doe, Jane"}],
    ]
    assert _indicator("700", record) == [("1", " "), ("1", " ")]
    assert _subfields("776", record) == [[{"z": "978-0-987654-32-1"}]]
    assert _indicator("776", record) == [("0", " ")]


def test_to_marc_empty_metadata():
    """An empty metadata object still emits placeholder 245 and 264 fields."""
    record = to_marc(PublicationMetadata())
    assert isinstance(record, MarcRecord)
    assert _tags(record) == ["245", "264"]
    assert _subfields("245", record) == [[{"a": "[Title not identified]"}]]
    assert _indicator("245", record) == [("0", "0")]
    assert _subfields("264", record) == [
        [
            {"a": "[Place of publication not identified] :"},
            {"b": "[publisher not identified],"},
            {"c": "[date of publication not identified]"},
        ]
    ]
    assert _indicator("264", record) == [(" ", "1")]


def test_to_marc_partial_metadata():
    """A title plus a single creator produces 100, 245 and placeholder 264."""
    metadata = PublicationMetadata(title="A Title", creator=["Solo, A"])
    record = to_marc(metadata)
    assert _tags(record) == ["100", "245", "264"]
    assert _subfields("100", record) == [[{"a": "Solo, A"}]]
    assert _indicator("100", record) == [("1", " ")]
    assert _subfields("245", record) == [[{"a": "A Title"}, {"c": "Solo, A"}]]
    assert _indicator("245", record) == [("1", "0")]
    assert _subfields("264", record) == [
        [
            {"a": "[Place of publication not identified] :"},
            {"b": "[publisher not identified],"},
            {"c": "[date of publication not identified]"},
        ]
    ]
    assert _indicator("264", record) == [(" ", "1")]


def test_to_marc_single_creator():
    """A single creator maps to a 100 field plus 245 subfield c."""
    record = to_marc(PublicationMetadata(creator=["Smith, John"]))
    assert _tags(record) == ["100", "245", "264"]
    assert _subfields("100", record) == [[{"a": "Smith, John"}]]
    assert _indicator("100", record) == [("1", " ")]
    assert _subfields("245", record) == [
        [{"a": "[Title not identified]"}, {"c": "Smith, John"}]
    ]
    assert _indicator("245", record) == [("1", "0")]


def test_to_marc_multiple_creators():
    """Multiple creators are joined into 245 subfield c and each gets a 700."""
    record = to_marc(PublicationMetadata(creator=["A, One", "B, Two", "C, Three"]))
    assert _tags(record) == ["245", "264", "700", "700", "700"]
    assert _subfields("245", record) == [
        [{"a": "[Title not identified]"}, {"c": "A, One ; B, Two ; C, Three"}]
    ]
    assert _subfields("700", record) == [
        [{"a": "A, One"}],
        [{"a": "B, Two"}],
        [{"a": "C, Three"}],
    ]
    assert _indicator("700", record) == [("1", " "), ("1", " "), ("1", " ")]


def test_to_marc_title_with_subtitle():
    """A title containing ' : ' is split into 245 subfields a and b."""
    record = to_marc(PublicationMetadata(title="Main : Sub"))
    assert _subfields("245", record) == [[{"a": "Main"}, {"b": "Sub"}]]
    assert _indicator("245", record) == [("0", "0")]


def test_to_marc_alt_title():
    """An alt title maps to a 246 field with indicator 3/blank."""
    record = to_marc(PublicationMetadata(alt_title=["An Alt Title"]))
    assert _subfields("246", record) == [[{"a": "An Alt Title"}]]
    assert _indicator("246", record) == [("3", " ")]


def test_to_marc_language_iso639_2b():
    """Language codes are converted to ISO 639-2/B in 041 subfield a."""
    assert _subfields("041", to_marc(PublicationMetadata(language="en"))) == [
        [{"a": "eng"}]
    ]
    assert _subfields("041", to_marc(PublicationMetadata(language="de"))) == [
        [{"a": "ger"}]
    ]
    assert _subfields("041", to_marc(PublicationMetadata(language="fr"))) == [
        [{"a": "fre"}]
    ]
    assert _indicator("041", to_marc(PublicationMetadata(language="en"))) == [
        (" ", " ")
    ]


def test_to_marc_unknown_language_omits_041():
    """An unconvertible language code produces no 041 field."""
    record = to_marc(PublicationMetadata(language="nonsense"))
    assert _fields_with_tag("041", record) == []
    assert _tags(record) == ["245", "264"]


def test_to_marc_doi():
    """A DOI maps to a 024 field with source-of-number subfield 2."""
    record = to_marc(PublicationMetadata(doi="10.1234/example.doi.12345"))
    assert _subfields("024", record) == [
        [{"a": "10.1234/example.doi.12345"}, {"2": "doi"}]
    ]
    assert _indicator("024", record) == [("7", " ")]


def test_to_marc_publisher_without_year():
    """Publishers without a year produce a 264 with a placeholder date."""
    record = to_marc(PublicationMetadata(publisher=["Springer", "ACM"]))
    assert _tags(record) == ["245", "264"]
    assert _subfields("264", record) == [
        [
            {"a": "[Place of publication not identified] :"},
            {"b": "Springer"},
            {"b": "ACM"},
            {"c": "[date of publication not identified]"},
        ]
    ]
    assert _indicator("264", record) == [(" ", "1")]


def test_to_marc_year_without_publisher():
    """A year without publisher fills in placeholder subfields a and b."""
    record = to_marc(PublicationMetadata(year="2023"))
    assert _tags(record) == ["245", "264"]
    assert _subfields("264", record) == [
        [
            {"a": "[Place of publication not identified] :"},
            {"b": "[publisher not identified],"},
            {"c": "2023"},
        ]
    ]
    assert _indicator("264", record) == [(" ", "1")]


def test_to_marc_e_isbn_takes_precedence_in_020():
    """With e_isbn set, only e_isbn values go into 020 as electronic
    resources; p_isbn values appear only in 776 subfield z."""
    record = to_marc(
        PublicationMetadata(p_isbn=["1111-1", "1111-2"], e_isbn=["2222-1", "2222-2"])
    )
    assert _tags(record) == ["020", "020", "245", "264", "776", "776"]
    assert _subfields("020", record) == [
        [{"a": "2222-1"}, {"q": "electronic resource"}],
        [{"a": "2222-2"}, {"q": "electronic resource"}],
    ]
    assert _indicator("020", record) == [(" ", " "), (" ", " ")]
    assert _subfields("776", record) == [[{"z": "1111-1"}], [{"z": "1111-2"}]]
    assert _indicator("776", record) == [("0", " "), ("0", " ")]


def test_to_marc_print_isbn_when_no_e_isbn():
    """Without e_isbn, p_isbn values go into 020 with a print qualifier and
    no 776 fields are emitted."""
    record = to_marc(PublicationMetadata(p_isbn=["1111-1", "1111-2"]))
    assert _tags(record) == ["020", "020", "245", "264"]
    assert _subfields("020", record) == [
        [{"a": "1111-1"}, {"q": "print resource"}],
        [{"a": "1111-2"}, {"q": "print resource"}],
    ]
    assert _indicator("020", record) == [(" ", " "), (" ", " ")]
    assert _subfields("776", record) == []


def test_to_marc_issns():
    """Print and electronic ISSNs both go into 490 subfield x, in that order."""
    record = to_marc(PublicationMetadata(p_issn="2345-6789", e_issn="1234-5678"))
    assert _subfields("490", record) == [[{"x": "2345-6789"}, {"x": "1234-5678"}]]
    assert _indicator("490", record) == [("0", " ")]
    record = to_marc(PublicationMetadata(e_issn="1234-5678"))
    assert _subfields("490", record) == [[{"x": "1234-5678"}]]
    record = to_marc(PublicationMetadata(p_issn="2345-6789"))
    assert _subfields("490", record) == [[{"x": "2345-6789"}]]


def test_to_marc_type_coar():
    """A COAR document type maps to a 655 field with source subfield 2."""
    record = to_marc(PublicationMetadata(type_coar="article"))
    assert _subfields("655", record) == [[{"a": "article"}, {"2": "coar"}]]
    assert _indicator("655", record) == [(" ", "7")]


def test_to_marc_filters_empty_values():
    """Empty title, publisher, year and doi produce placeholder fields; empty
    creators are excluded from 245 subfield c, but 700 fields are still
    emitted for every creator entry."""
    record = to_marc(
        PublicationMetadata(
            title="",
            creator=["", "Valid, Name"],
            publisher=[""],
            year="",
            doi="",
        )
    )
    assert _tags(record) == ["245", "264", "700", "700"]
    assert _subfields("245", record) == [
        [{"a": "[Title not identified]"}, {"c": "Valid, Name"}]
    ]
    assert _indicator("245", record) == [("0", "0")]
    assert _subfields("264", record) == [
        [
            {"a": "[Place of publication not identified] :"},
            {"b": "[publisher not identified],"},
            {"c": "[date of publication not identified]"},
        ]
    ]
    assert _indicator("264", record) == [(" ", "1")]
    assert _subfields("700", record) == [[{"a": ""}], [{"a": "Valid, Name"}]]
    assert _indicator("700", record) == [("1", " "), ("1", " ")]


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
