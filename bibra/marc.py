"""Conversion from PublicationMetadata to MARC21 records."""

from langcodes import Language
from langcodes.tag_parser import LanguageTagError
from pymarc import Field, Indicators, Record, Subfield

from bibra.types import MarcRecord, PublicationMetadata

# MARC indicators and static subfields
_ISBN_020_IND1 = " "
_ISBN_020_IND2 = " "
_ISBN_020_SUBFIELD_Q = "electronic resource"
_ISBN_020_SUBFIELD_Q_PRINT = "print resource"

_DOI_024_IND1 = "7"
_DOI_024_IND2 = " "
_DOI_024_SUBFIELD_2 = "doi"

_LANGUAGE_041_IND1 = " "
_LANGUAGE_041_IND2 = " "

_CREATOR_100_IND1 = "1"
_CREATOR_100_IND2 = " "

_TITLE_245_IND1 = "0"
_TITLE_245_IND2 = "0"
_TITLE_245_SUBFIELD_A = "[Title not identified]"

_ALT_TITLE_246_IND1 = "3"
_ALT_TITLE_246_IND2 = " "

_PUBLISHER_264_IND1 = " "
_PUBLISHER_264_IND2 = "1"
_PUBLISHER_264_SUBFIELD_A = "[Place of publication not identified] :"
_PUBLISHER_264_SUBFIELD_B = "[publisher not identified],"
_PUBLISHER_264_SUBFIELD_C = "[date of publication not identified]"

_ISSN_490_IND1 = "0"
_ISSN_490_IND2 = " "

_GENRE_655_IND1 = " "
_GENRE_655_IND2 = "7"
_GENRE_655_SUBFIELD_2 = "coar"

_CREATOR_700_IND1 = "1"
_CREATOR_700_IND2 = " "

_ISBN_776_IND1 = "0"
_ISBN_776_IND2 = " "


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

    # 020 - ISBN ($a)
    if metadata.e_isbn:
        for isbn in metadata.e_isbn:
            record.add_field(
                _field(
                    "020",
                    [{"a": isbn, "q": _ISBN_020_SUBFIELD_Q}],
                    _ISBN_020_IND1,
                    _ISBN_020_IND2,
                )
            )
    else:
        for isbn in metadata.p_isbn:
            record.add_field(
                _field(
                    "020",
                    [{"a": isbn, "q": _ISBN_020_SUBFIELD_Q_PRINT}],
                    _ISBN_020_IND1,
                    _ISBN_020_IND2,
                )
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

    # 041 - Language ($a)
    if metadata.language:
        try:
            lang = Language.get(metadata.language).to_alpha3(variant="B")
        except (LookupError, LanguageTagError):
            lang = None
        if lang:
            record.add_field(
                _field("041", [{"a": lang}], _LANGUAGE_041_IND1, _LANGUAGE_041_IND2)
            )

    # 100 - Creator ($a)
    if metadata.creator and len(metadata.creator) == 1:
        record.add_field(
            _field(
                "100",
                [{"a": metadata.creator[0]}],
                _CREATOR_100_IND1,
                _CREATOR_100_IND2,
            )
        )

    # 245 - Title ($a), alt title ($b), creators ($c)
    title_subfields = []
    if metadata.title:
        titles = metadata.title.split(" : ", 1)
        title_subfields.append({"a": titles[0]})
        if len(titles) > 1:
            title_subfields.append({"b": titles[1]})
    else:
        title_subfields.append({"a": _TITLE_245_SUBFIELD_A})
    creators = [creator for creator in metadata.creator if creator]
    if creators:
        title_subfields.append({"c": " ; ".join(creators)})
    record.add_field(
        _field(
            "245",
            title_subfields,
            _TITLE_245_IND1,
            _TITLE_245_IND2,
        )
    )

    # 246 - Alt title ($a)
    for alt_title in metadata.alt_title:
        record.add_field(
            _field(
                "246",
                [{"a": alt_title}],
                _ALT_TITLE_246_IND1,
                _ALT_TITLE_246_IND2,
            )
        )

    # 264 - Publisher and year: place ($a), publisher ($b), year ($c).
    publisher_subfields = [{"a": _PUBLISHER_264_SUBFIELD_A}]
    publishers = [publisher for publisher in metadata.publisher if publisher]
    if publishers:
        publisher_subfields.extend([{"b": publisher} for publisher in publishers])
    else:
        publisher_subfields.append({"b": _PUBLISHER_264_SUBFIELD_B})
    if metadata.year:
        publisher_subfields.append({"c": metadata.year})
    else:
        publisher_subfields.append({"c": _PUBLISHER_264_SUBFIELD_C})
    record.add_field(
        _field("264", publisher_subfields, _PUBLISHER_264_IND1, _PUBLISHER_264_IND2)
    )

    # 490 - ISSNs (print and electronic, both in $x)
    issn_subfields = []
    if metadata.p_issn:
        issn_subfields.append({"x": metadata.p_issn})
    if metadata.e_issn:
        issn_subfields.append({"x": metadata.e_issn})
    if issn_subfields:
        record.add_field(_field("490", issn_subfields, _ISSN_490_IND1, _ISSN_490_IND2))

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

    # 700 - Creators ($a)
    if metadata.creator and len(metadata.creator) > 1:
        for creator in metadata.creator:
            record.add_field(
                _field("700", [{"a": creator}], _CREATOR_700_IND1, _CREATOR_700_IND2)
            )

    # 776 - p ISBN ($z)
    if metadata.e_isbn:
        for isbn in metadata.p_isbn:
            if isbn:
                record.add_field(
                    _field("776", [{"z": isbn}], _ISBN_776_IND1, _ISBN_776_IND2)
                )

    return record


def to_marc(metadata: PublicationMetadata) -> MarcRecord:
    """Convert publication metadata to a MARC21 record."""
    fields = _build_pymarc_record(metadata).as_dict()["fields"]
    return MarcRecord.model_validate({"fields": fields})
