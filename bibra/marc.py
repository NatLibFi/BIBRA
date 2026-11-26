"""Conversion from PublicationMetadata to MARC21 records."""

from pymarc import Field, Indicators, Record, Subfield

from bibra.types import MarcRecord, PublicationMetadata

# MARC indicators and static subfields
_ISBN_020_IND1 = " "
_ISBN_020_IND2 = " "

_ISSN_022_IND1 = " "
_ISSN_022_IND2 = " "

_DOI_024_IND1 = "7"
_DOI_024_IND2 = " "
_DOI_024_SUBFIELD_2 = "doi"

_LANGUAGE_041_IND1 = " "
_LANGUAGE_041_IND2 = "7"
_LANGUAGE_041_SUBFIELD_2 = "bcp47"

_TITLE_245_IND1 = "0"
_TITLE_245_IND2 = "0"

_PUBLISHER_264_IND1 = " "
_PUBLISHER_264_IND2 = "1"
_PUBLISHER_264_SUBFIELD_A = "[Place of publication not identified] :"
_PUBLISHER_264_SUBFIELD_B = "[publisher not identified],"

_GENRE_655_IND1 = " "
_GENRE_655_IND2 = "7"
_GENRE_655_SUBFIELD_2 = "coar"


def _field(
    tag: str,
    subfields: list[dict[str, str]],
    ind1: str,
    ind2: str,
) -> Field:
    """Build a pymarc Field from single-key subfield mappings."""
    pymarc_subfields = [
        Subfield(code=code, value=value)
        for subfield in subfields
        for code, value in subfield.items()
    ]
    return Field(
        tag=tag,
        indicators=Indicators(ind1, ind2),
        subfields=pymarc_subfields,
    )


def _build_pymarc_record(metadata: PublicationMetadata) -> Record:
    """Build a pymarc Record from publication metadata."""
    record = Record()

    # 020 - ISBNs (print and electronic, both in $a)
    for isbn in metadata.p_isbn:
        if isbn:
            record.add_field(
                _field("020", [{"a": isbn}], _ISBN_020_IND1, _ISBN_020_IND2)
            )
    for isbn in metadata.e_isbn:
        if isbn:
            record.add_field(
                _field("020", [{"a": isbn}], _ISBN_020_IND1, _ISBN_020_IND2)
            )

    # 022 - ISSNs (print and electronic, both in $a)
    if metadata.p_issn:
        record.add_field(
            _field("022", [{"a": metadata.p_issn}], _ISSN_022_IND1, _ISSN_022_IND2)
        )
    if metadata.e_issn:
        record.add_field(
            _field("022", [{"a": metadata.e_issn}], _ISSN_022_IND1, _ISSN_022_IND2)
        )

    # 024 - DOI ($a), source of number or code ($2)
    if metadata.doi:
        record.add_field(
            _field(
                "024",
                [{"a": metadata.doi}, {"2": _DOI_024_SUBFIELD_2}],
                _DOI_024_IND1,
                _DOI_024_IND2,
            )
        )

    # 041 - Language ($a), source of code ($2)
    if metadata.language:
        record.add_field(
            _field(
                "041",
                [{"a": metadata.language, "2": _LANGUAGE_041_SUBFIELD_2}],
                _LANGUAGE_041_IND1,
                _LANGUAGE_041_IND2,
            )
        )

    # 245 - Title ($a), alt title ($b), creators ($c)
    title_subfields = []
    if metadata.title:
        title_subfields.append({"a": metadata.title})
    if metadata.alt_title:
        title_subfields.append({"b": metadata.alt_title})
    creators = [creator for creator in metadata.creator if creator]
    if creators:
        title_subfields.append({"c": " ; ".join(creators)})
    if title_subfields:
        record.add_field(
            _field(
                "245",
                title_subfields,
                _TITLE_245_IND1,
                _TITLE_245_IND2,
            )
        )

    # 264 - Publisher and year: place ($a), publisher ($b), year ($c)
    publisher_subfields = []
    publishers = [publisher for publisher in metadata.publisher if publisher]
    if publishers:
        publisher_subfields.extend([{"b": publisher} for publisher in publishers])
    elif metadata.year:
        publisher_subfields.append({"b": _PUBLISHER_264_SUBFIELD_B})
    if metadata.year:
        publisher_subfields.append({"c": metadata.year})
    if publisher_subfields:
        publisher_subfields.insert(0, {"a": _PUBLISHER_264_SUBFIELD_A})
        record.add_field(
            _field("264", publisher_subfields, _PUBLISHER_264_IND1, _PUBLISHER_264_IND2)
        )

    # 655 - Document type (COAR) ($a), source of term ($2)
    if metadata.type_coar:
        record.add_field(
            _field(
                "655",
                [{"a": metadata.type_coar}, {"2": _GENRE_655_SUBFIELD_2}],
                _GENRE_655_IND1,
                _GENRE_655_IND2,
            )
        )

    return record


def to_marc(metadata: PublicationMetadata) -> MarcRecord:
    """Convert publication metadata to a MARC21 record."""
    fields = _build_pymarc_record(metadata).as_dict()["fields"]
    return MarcRecord.model_validate({"fields": fields})
