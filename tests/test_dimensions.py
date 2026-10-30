import pytest

import harvest
from harvest import add_dimensions_metadata, match_dimensions_authors, name_key


def creator(family, given=None, orcid=None):
    person = {"family_name": family, "given_name": given, "type": "personal"}
    if orcid:
        person["identifiers"] = [{"scheme": "orcid", "identifier": orcid}]
    return {"person_or_org": person}


def org(name):
    return {"person_or_org": {"name": name, "type": "organizational"}}


def dim(last, first=None, orcid=None, affiliations=None):
    return {
        "last_name": last,
        "first_name": first,
        "orcid": [orcid] if orcid else None,
        "affiliations": affiliations,
    }


def matched_names(pairs):
    return [
        (dimensions_author["last_name"], c["person_or_org"]["family_name"])
        for dimensions_author, c in pairs
    ]


@pytest.fixture
def dimensions_publication(monkeypatch):
    # Replace the Dimensions API with a publication the test can fill in
    publication = {"authors": []}

    class Response:
        json = {"publications": [publication]}

    class Dsl:
        def query_iterative(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(harvest.dimcli, "login", lambda **kwargs: None)
    monkeypatch.setattr(harvest.dimcli, "Dsl", Dsl)
    return publication


def test_name_key():
    assert name_key("Müller-Schmidt") == name_key("Muller Schmidt")
    assert name_key(None) == ""


def test_match_skips_collaboration():
    pairs = match_dimensions_authors(
        [dim("Smith", "J"), dim("Lee", "K")],
        [org("LIGO Collaboration"), creator("Smith", "John"), creator("Lee", "Kim")],
    )
    assert matched_names(pairs) == [("Smith", "Smith"), ("Lee", "Lee")]


def test_match_skips_author_missing_from_dimensions():
    pairs = match_dimensions_authors(
        [dim("Thomas", "Lucy"), dim("Johar", "Sam"), dim("Boyle", "Michael")],
        [
            creator("Thomas", "Lucy M."),
            creator("Chatziioannou", "Katerina"),
            creator("Johar", "Sam"),
            creator("Boyle", "Michael"),
        ],
    )
    assert matched_names(pairs) == [
        ("Thomas", "Thomas"),
        ("Johar", "Johar"),
        ("Boyle", "Boyle"),
    ]


def test_match_by_orcid_and_repeated_names():
    pairs = match_dimensions_authors(
        [
            dim("Zhang", "Wei"),
            dim("Wang", "Y", orcid="0000-0001-2345-6789"),
            dim("Zhang", "Wei"),
        ],
        [
            creator("Zhang", "Wei"),
            creator("Wong", "Yan", orcid="https://orcid.org/0000-0001-2345-6789"),
            creator("Zhang", "Wei"),
            org("X Collaboration"),
        ],
    )
    assert [c for _, c in pairs] == [
        creator("Zhang", "Wei"),
        creator("Wong", "Yan", orcid="https://orcid.org/0000-0001-2345-6789"),
        creator("Zhang", "Wei"),
    ]
    assert pairs[0][1] is not pairs[2][1]


def test_no_match_when_initials_differ():
    assert match_dimensions_authors(
        [dim("Smith", "A")], [creator("Smith", "Bob"), org("Y")]
    ) == []


def test_mismatch_adds_data_to_matched_authors(dimensions_publication):
    dimensions_publication["authors"] = [
        dim(
            "Thomas",
            "Lucy",
            orcid="0000-0003-3271-6436",
            affiliations=[{"id": "grid.20861.3d", "raw_affiliation": "Caltech"}],
        ),
        dim(
            "Boyle",
            "Michael",
            affiliations=[{"id": None, "raw_affiliation": "Cornell"}],
        ),
    ]
    metadata = {
        "metadata": {
            "creators": [
                creator("Thomas", "Lucy M."),
                creator("Chatziioannou", "Katerina"),
                creator("Boyle", "Michael"),
            ]
        }
    }
    metadata, message = add_dimensions_metadata(metadata, "10.1/test", "")
    thomas, chatziioannou, boyle = metadata["metadata"]["creators"]
    assert thomas["person_or_org"]["identifiers"] == [
        {"scheme": "orcid", "identifier": "0000-0003-3271-6436"}
    ]
    assert thomas["affiliations"] == [{"id": "05dxps055", "name": "Caltech"}]
    assert "affiliations" not in chatziioannou
    assert boyle["affiliations"] == [{"name": "Cornell"}]
    assert "author count is off" in message


def test_no_warning_when_nothing_added(dimensions_publication):
    dimensions_publication["authors"] = [dim("Thomas", "Lucy")]
    metadata = {
        "metadata": {
            "creators": [creator("Thomas", "Lucy M."), creator("Boyle", "Michael")]
        }
    }
    metadata, message = add_dimensions_metadata(metadata, "10.1/test", "start")
    assert message == "start"


def test_equal_counts_match_by_position(dimensions_publication):
    dimensions_publication["authors"] = [
        dim("Different", "Name", orcid="0000-0002-0000-0001")
    ]
    metadata = {"metadata": {"creators": [creator("Thomas", "Lucy")]}}
    metadata, message = add_dimensions_metadata(metadata, "10.1/test", "")
    person = metadata["metadata"]["creators"][0]["person_or_org"]
    assert person["identifiers"][0]["identifier"] == "0000-0002-0000-0001"
    assert "author count is off" not in message
