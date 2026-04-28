from scripts import harvest_foia


def test_build_search_params_matches_live_request_shape() -> None:
    params = harvest_foia.build_search_params("F-2017-13804", page_number=1, start=0, limit=10)

    assert params["searchText"] == "*"
    assert params["caseNumber"] == "F-2017-13804"
    assert params["limit"] == 10
    assert params["collectionMatch"] == "false"
    assert params["postedBeginDate"] == "false"


def test_map_release_status_handles_known_foia_codes() -> None:
    assert harvest_foia.map_release_status("RIFPUB") == "RELEASE IN FULL"
    assert harvest_foia.map_release_status("RIPPUB") == "RELEASE IN PART"


def test_normalize_record_uses_existing_manifest_schema() -> None:
    api_record = {
        "casenumber": "F-2017-13804",
        "pdfLink": "DOCUMENTS/FOIA_Aug2019_2020/F-2017-13804/DOC_0C06697823/C06697823.pdf",
        "subject": "Sample live result",
        "docdate": "1996-05-15T00:00:00",
        "posteddate": "2020-02-07T00:00:00",
        "releasedecision": "RIFPUB",
    }

    record = harvest_foia.normalize_record(api_record, "F-2017-13804")

    assert record.id == "C06697823"
    assert record.case_number == "F-2017-13804"
    assert record.title == "Sample live result"
    assert record.date == "1996-05-15"
    assert record.source_pdf_url == (
        "https://foia.state.gov/DOCUMENTS/FOIA_Aug2019_2020/F-2017-13804/"
        "DOC_0C06697823/C06697823.pdf"
    )
    assert record.release_status == "RELEASE IN FULL"
    assert record.text_path == "data/text/C06697823.txt"
