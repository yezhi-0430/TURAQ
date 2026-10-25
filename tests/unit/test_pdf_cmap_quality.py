"""Standard CID decoding, source preservation and extraction quality regressions."""

import io
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)


def cid_pdf(*, ordering="GB1", form=False, cycle=False, oversized=False):
    from pdfminer.cmapdb import CMapDB

    mapping = CMapDB.get_unicode_map("Adobe-GB1", vertical=False).cid2unichr
    cids = [next(cid for cid, char in mapping.items() if char == target) for target in "营业收入"]
    bits = bytearray(max(cids) // 8 + 1)
    for cid in cids:
        bits[cid // 8] |= 128 >> (cid % 8)
    subset = DecodedStreamObject()
    subset.set_data(b"x" * 8193 if oversized else bytes(bits))
    writer = PdfWriter()
    page = writer.add_blank_page(600, 400)
    child = DictionaryObject(
        {
            NameObject("/Subtype"): NameObject("/CIDFontType0"),
            NameObject("/BaseFont"): NameObject("/MiniGB"),
            NameObject("/DW"): NumberObject(1000),
            NameObject("/CIDSystemInfo"): DictionaryObject(
                {
                    NameObject("/Registry"): TextStringObject("Adobe"),
                    NameObject("/Ordering"): TextStringObject(ordering),
                    NameObject("/Supplement"): NumberObject(4),
                }
            ),
            NameObject("/FontDescriptor"): DictionaryObject({NameObject("/CIDSet"): subset}),
        }
    )
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type0"),
            NameObject("/BaseFont"): NameObject("/MiniGB"),
            NameObject("/Encoding"): NameObject("/Identity-H"),
            NameObject("/DescendantFonts"): ArrayObject([child]),
        }
    )
    fonts = DictionaryObject(
        {
            NameObject("/F0"): font,
            NameObject("/F1"): DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/Font"),
                    NameObject("/Subtype"): NameObject("/Type1"),
                    NameObject("/BaseFont"): NameObject("/Helvetica"),
                }
            ),
        }
    )
    resources = DictionaryObject({NameObject("/Font"): fonts})
    page[NameObject("/Resources")] = resources
    raw = (
        "BT /F0 12 Tf 10 200 Td <"
        + "".join(f"{cid:04x}" for cid in cids)
        + "> Tj /F1 12 Tf 150 0 Td (337,488 2024) Tj ET"
    ).encode()
    content = DecodedStreamObject()
    if form or cycle:
        xobject = DecodedStreamObject()
        xobject.update(
            {
                NameObject("/Subtype"): NameObject("/Form"),
                NameObject("/BBox"): ArrayObject([NumberObject(x) for x in (0, 0, 600, 400)]),
            }
        )
        xobject.set_data(b"/Inner Do" if cycle else raw)
        ref = writer._add_object(xobject)
        if cycle:
            xobject[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/XObject"): DictionaryObject({NameObject("/Inner"): ref})}
            )
        resources[NameObject("/XObject")] = DictionaryObject({NameObject("/Outer"): ref})
        content.set_data(b"/Outer Do")
    else:
        content.set_data(raw)
    page[NameObject("/Contents")] = content
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_real_cid_pdf_reproduces_old_failure_and_repairs_chinese_without_editing_bytes():
    from app.document_parser import extract

    data = cid_pdf()
    assert "营业收入" not in PdfReader(io.BytesIO(data)).pages[0].extract_text()
    result = extract(data)
    assert "营业收入" in result["pages"][0]["text"]
    assert "337,488" in result["pages"][0]["text"]
    assert "2024" in result["pages"][0]["text"]
    assert result["parser_version"] == "pypdf-standard-cid-v2"
    assert result["pages"][0]["extraction"]["standard_cid_fonts"] == 1
    assert "营业收入" not in PdfReader(io.BytesIO(data)).pages[0].extract_text()


def test_form_inherits_page_fonts_and_is_decoded():
    from app.document_parser import extract

    assert "营业收入" in extract(cid_pdf(form=True))["pages"][0]["text"]


@pytest.mark.parametrize(
    "kwargs", [dict(ordering="../../hostile"), dict(cycle=True), dict(oversized=True)]
)
def test_unsupported_fonts_and_resource_budgets_fail_closed(kwargs):
    from app.document_parser import extract

    with pytest.raises(ValueError):
        extract(cid_pdf(**kwargs))


def test_existing_unicode_map_is_preserved_and_unused_font_is_ignored():
    from app.pdf_cmap import StandardCIDMapper

    reader = PdfReader(io.BytesIO(cid_pdf()))
    page = reader.pages[0]
    font = page["/Resources"]["/Font"]["/F0"]
    sentinel = DecodedStreamObject()
    sentinel.set_data(b"already provided")
    font[NameObject("/ToUnicode")] = sentinel
    page["/Resources"]["/Font"][NameObject("/Unused")] = DictionaryObject(
        {
            NameObject("/Subtype"): NameObject("/Type0"),
            NameObject("/Encoding"): NameObject("/Identity-H"),
        }
    )
    assert StandardCIDMapper(reader).prepare_page(page) == 0
    assert font["/ToUnicode"].get_data() == b"already provided"


@pytest.mark.parametrize("failure", ["missing", "partial"])
def test_missing_or_partial_standard_map_never_becomes_usable_text(monkeypatch, failure):
    import app.pdf_cmap as compat
    from app.document_parser import extract

    def unavailable(*args):
        raise ImportError("not installed")

    monkeypatch.setattr(
        compat, "load_standard_map", unavailable if failure == "missing" else lambda *args: {}
    )
    with pytest.raises(ValueError):
        extract(cid_pdf())


@pytest.mark.parametrize(
    "text",
    [
        "English annual report 2024 revenue 123.45",
        "123,456 2024",
        "中文年报营业收入",
        "日本語の資料",
        "تقرير البنك السنوي باللغة العربية",
        "短句",
        "",
    ],
)
def test_normal_languages_and_numeric_pages_are_not_garbled_just_for_lacking_han(text):
    from app.pdf_text_quality import text_quality_issue

    assert text_quality_issue(text) is None


def test_observed_cmb_garbled_text_and_replacement_runs_are_detected():
    import json

    from app.pdf_text_quality import text_quality_issue

    root = Path(__file__).resolve().parents[2]
    pages = json.loads(
        (root / "evaluations/turaq/unseen-reports/sources/cmb-2024.pages.json").read_text(
            encoding="utf-8"
        )
    )
    assert text_quality_issue(pages[13]["text"])
    assert text_quality_issue("\ufffd" * 20 + " 123456")
    assert text_quality_issue("(cid:123)" * 20)


def test_scope_boundary_check_is_by_registered_id_not_an_offsetting_empty_row_count():
    from app.unseen_report_validation import scope_boundaries_ok

    kinds = ["before_publication", "wrong_security", "wrong_report", "other_owner", "withdrawn"]
    cases = [
        dict(id=f"b{i}", validation_kind="boundary", boundary_kind=kind)
        for i, kind in enumerate(kinds)
    ]
    cases.append(dict(id="fact", validation_kind="fact"))
    rows = [dict(id=c["id"], eligible_resources=0, units=[], error=None) for c in cases]
    assert scope_boundaries_ok(rows, cases)
    # One leaked boundary and one erroneously empty fact still yield five empty rows.
    rows[0].update(eligible_resources=1, units=["leak"])
    assert sum(r["eligible_resources"] == 0 for r in rows) == 5
    assert not scope_boundaries_ok(rows, cases)
    assert not scope_boundaries_ok(rows[1:], cases)
    assert not scope_boundaries_ok(rows + [rows[1]], cases)


@pytest.mark.parametrize(
    "message",
    [
        "PDF文字编码暂不支持，未生成文档事实",
        "PDF结构过于复杂，未生成文档事实",
        "PDF文字编码异常，未生成文档事实；OCR尚未接通",
    ],
)
def test_known_quality_errors_reach_upload_and_disclosure_without_duplicate_suffix(
    monkeypatch, message
):
    import json
    from types import SimpleNamespace

    from app.analysis import quality
    from app.disclosures import parser_error

    output = json.dumps(dict(error=message), ensure_ascii=False).encode()
    monkeypatch.setattr(quality, "corpus", lambda: dict(documents={}))
    monkeypatch.setattr(
        quality.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout=output)
    )
    with pytest.raises(ValueError, match=message):
        quality.parse_pdf(b"%PDF-test")
    assert parser_error(output).count("未生成文档事实") == 1


def test_unknown_child_error_never_reaches_upload(monkeypatch):
    import json
    from types import SimpleNamespace

    from app.analysis import quality

    monkeypatch.setattr(quality, "corpus", lambda: dict(documents={}))
    output = json.dumps(dict(error="secret private path")).encode()
    monkeypatch.setattr(
        quality.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=1, stdout=output)
    )
    with pytest.raises(ValueError) as caught:
        quality.parse_pdf(b"%PDF-test")
    assert "secret" not in str(caught.value)


def test_new_extraction_relocalizes_duplicate_anchors_without_changing_values_or_pdf():
    from app.pdf_cmap_validation import relocate_references

    old_text = "basic 5.66 diluted 5.66"
    new_text = "新表头\nbasic 5.66  diluted 5.66"
    old = dict(
        documents={"d": dict(pdf_sha256="same", text_pages=[dict(text=old_text)])},
        gold={
            "basic": dict(
                status="supported",
                value="5.66",
                unit="元",
                allowed_anchors=[dict(document_id="d", page=1, start=6, end=10, quote="5.66")],
            )
        },
        cases=[dict(id="basic")],
    )
    new_docs = {"d": dict(pdf_sha256="same", text_pages=[dict(text=new_text)])}
    gold, changes = relocate_references(old, new_docs)
    anchor = gold["basic"]["allowed_anchors"][0]
    assert anchor["start"] == new_text.index("5.66")
    assert gold["basic"]["value"] == "5.66" and gold["basic"]["unit"] == "元"
    assert changes[0]["case_id"] == "basic"
    assert old["gold"]["basic"]["allowed_anchors"][0]["start"] == 6
    new_docs["d"]["text_pages"][0]["text"] += " 5.66"
    with pytest.raises(ValueError):
        relocate_references(old, new_docs)
    new_docs["d"]["pdf_sha256"] = "changed"
    with pytest.raises(ValueError):
        relocate_references(old, new_docs)


def test_actual_glyph_omitted_from_declared_cidset_is_not_silently_returned():
    from app.document_parser import extract

    reader = PdfReader(io.BytesIO(cid_pdf()))
    font = reader.pages[0]["/Resources"]["/Font"]["/F0"]
    subset = font["/DescendantFonts"][0]["/FontDescriptor"]["/CIDSet"]
    bits = bytearray(subset.get_data())
    bits[4239 // 8] &= ~(128 >> (4239 % 8))
    subset.set_data(bytes(bits))
    writer = PdfWriter()
    writer.append(reader)
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(ValueError):
        extract(output.getvalue())


def test_repaired_font_rechecks_new_text_operations_and_standard_map_without_subset():
    from app.document_parser import extract

    reader = PdfReader(io.BytesIO(cid_pdf()))
    font = reader.pages[0]["/Resources"]["/Font"]["/F0"]
    del font["/DescendantFonts"][0]["/FontDescriptor"]["/CIDSet"]
    stream = reader.pages[0]["/Contents"]
    stream.set_data(stream.get_data() + b" BT /F0 12 Tf <ffff> Tj ET")
    writer = PdfWriter()
    writer.append(reader)
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(ValueError):
        extract(output.getvalue())


def test_form_depending_only_on_parent_font_state_fails_instead_of_emitting_glyph_codes():
    from app.document_parser import extract

    reader = PdfReader(io.BytesIO(cid_pdf(form=True)))
    form = reader.pages[0]["/Resources"]["/XObject"]["/Outer"]
    form.set_data(form.get_data().replace(b"/F0 12 Tf", b""))
    reader.pages[0]["/Contents"].set_data(b"BT /F0 12 Tf ET /Outer Do")
    writer = PdfWriter()
    writer.append(reader)
    output = io.BytesIO()
    writer.write(output)
    with pytest.raises(ValueError):
        extract(output.getvalue())


@pytest.mark.parametrize(
    "mutation", [None, "issuer", "metric", "period", "prefix", "missing", "duplicate", "leak"]
)
def test_validation_runner_enforces_registered_issuer_and_complete_question_set(mutation):
    from copy import deepcopy

    from app.pdf_cmap_validation import validate_registered_questions

    doc = dict(
        symbol="600887.SH",
        report_period="2024",
        published_date="2025-04-30",
        selected_pages=list(range(1, 33)),
    )
    fact = dict(
        id="f",
        validation_kind="fact",
        document_ids=["new"],
        context_pages={"new": list(range(1, 33))},
        symbol="600887.SH",
        metric="营业收入",
        period="2024",
        report_period="2024",
        owner="pilot-a",
        as_of="2025-06-01",
    )
    cases = [fact]
    gold = {"f": dict(status="supported")}
    kinds = [
        "future_period",
        "before_publication",
        "wrong_security",
        "wrong_report",
        "other_owner",
        "withdrawn",
    ]
    reasons = [
        "period_not_present",
        "not_yet_public",
        "wrong_security",
        "sources_unavailable",
        "sources_unavailable",
        "sources_unavailable",
    ]
    for i, (kind, reason) in enumerate(zip(kinds, reasons, strict=True)):
        case = dict(deepcopy(fact), id=f"b{i}", validation_kind="boundary", boundary_kind=kind)
        if i == 0:
            case["period"] = "2026"
        elif i == 1:
            case["as_of"] = doc["published_date"]
        elif i == 2:
            case["symbol"] = "999999.SH"
        elif i == 3:
            case["report_period"] = "2023"
        elif i == 4:
            case["owner"] = "another"
        else:
            case["withdrawn"] = True
        cases.append(case)
        gold[case["id"]] = dict(status="insufficient", reason_code=reason)
    corpus = dict(documents={"new": doc}, cases=cases, gold=gold)
    if mutation == "issuer":
        doc["symbol"] = "wrong"
    elif mutation == "metric":
        fact["metric"] = "easy replacement"
    elif mutation == "period":
        fact["period"] = "2023"
    elif mutation == "prefix":
        fact["context_pages"]["new"][-1] = 33
    elif mutation == "missing":
        cases.pop()
    elif mutation == "duplicate":
        cases[-1] = deepcopy(cases[-2])
    elif mutation == "leak":
        cases[-1]["withdrawn"] = False
    args = (corpus, [dict(metric="营业收入", period="2024")], {"new": "600887.SH"})
    if mutation is None:
        validate_registered_questions(*args)
    else:
        with pytest.raises(ValueError):
            validate_registered_questions(*args)
