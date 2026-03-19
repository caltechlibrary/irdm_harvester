import os, argparse

from caltechdata_api import caltechdata_write
from datetime import datetime
from traceback import format_exc
from utils import format_error

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a template record in CaltechAUTHORS"
    )
    parser.add_argument("harvest_type", help="california_tech")
    parser.add_argument("-issue", help="Issue number")
    parser.add_argument("-volume", help="Volume number")
    parser.add_argument("-date", help="Publication date (YYYY-MM-DD)")
    parser.add_argument("-test", action="store_true", help="Use the test environment")
    args = parser.parse_args()

    try:
        formatted_date = datetime.strptime(args.date, "%Y-%m-%d").strftime("%B %-d, %Y")
    except ValueError:
        raise ValueError(f"Invalid date format (expected YYYY-MM-DD): {args.date}")

    token = os.getenv("RDMTOK")
    harvest_type = args.harvest_type

    if args.test:
        production = False
    else:
        production = True

    if harvest_type == "california_tech":

        if production:
            community = "2de36d2e-df7d-4daa-85c2-31334ffec356"
        else:
            community = "8f398a9c-4c33-48ae-a60e-c5c96438121c"

        metadata = {
            "custom_fields": {
                "caltech:publication_status": [{"id": "published"}],
                "imprint:imprint": {"place": "Pasadena, CA"},
                "journal:journal": {
                    "issue": args.issue,
                    "title": "California Tech",
                    "volume": args.volume,
                },
            },
            "metadata": {
                "additional_titles": [
                    {
                        "lang": {"id": "eng"},
                        "title": "Tech",
                        "type": {"id": "alternative-title"},
                    }
                ],
                "contributors": [
                    {
                        "person_or_org": {
                            "family_name": "Wilson",
                            "given_name": "Damien",
                            "identifiers": [
                                {"identifier": "Wilson-Damien", "scheme": "clpid"}
                            ],
                            "name": "Wilson, Damien",
                            "type": "personal",
                        },
                        "role": {"id": "editor"},
                    }
                ],
                "creators": [
                    {
                        "affiliations": [{"id": "05dxps055"}],
                        "person_or_org": {
                            "identifiers": [
                                {
                                    "identifier": "Associated-Students-of-the-California-Institute-of-Technology",
                                    "scheme": "clpid",
                                }
                            ],
                            "name": "Associated Students of the California Institute of Technology, Inc.",
                            "type": "organizational",
                        },
                        "role": {"id": "issuing-body"},
                    }
                ],
                "languages": [{"id": "eng"}],
                "publication_date": args.date,
                "publisher": "California Institute of Technology",
                "related_identifiers": [
                    {
                        "identifier": "https://tech.caltech.edu/",
                        "relation_type": {"id": "ispublishedin"},
                        "resource_type": {"id": "publication-newspaper"},
                        "scheme": "url",
                    }
                ],
                "resource_type": {"id": "publication-newspaperissue"},
                "rights": [{"id": "default"}],
                "subjects": [{"subject": "Caltech student newspaper"}],
                "title": f"California Tech, v. {args.volume}, no. {args.issue}, {formatted_date}",
                "version": "Published",
            },
        }
        try:
            response = caltechdata_write(
                metadata,
                token,
                production=production,
                authors=True,
                community=community,
                publish=False,
            )
            print("templae created", response)
        except Exception as e:
            cleaned = format_error(format_exc())
            print(
                f"error= system error with writing metadata to CaltechAUTHORS {cleaned}"
            )
