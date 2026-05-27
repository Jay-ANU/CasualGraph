from rag.source_titles import display_document_title


def test_display_document_title_prefers_source_when_chunk_title_is_stale():
    assert display_document_title(
        {
            "document_id": "aa_sustainability_report_2022_20260505062611",
            "document_title": "aa-sustainability-report-2022",
            "source": "63ce4de69503662010f3a660_Apple_Pollution Emissions.pdf",
        }
    ) == "Apple Pollution Emissions"


def test_display_document_title_keeps_matching_title():
    assert display_document_title(
        {
            "document_id": "aa_sustainability_report_2022_20260501043104",
            "document_title": "aa-sustainability-report-2022",
            "source": "aa-sustainability-report-2022.pdf",
        }
    ) == "aa sustainability report 2022"
