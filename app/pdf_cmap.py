"""Read-only standard Adobe CID compatibility; no guessed words or company-specific maps."""

from functools import lru_cache

from pypdf.generic import ContentStream, DecodedStreamObject, NameObject

FONT_ERROR = "PDF文字编码暂不支持，未生成文档事实"
STRUCTURE_ERROR = "PDF结构过于复杂，未生成文档事实"
COLLECTIONS = {"GB1", "CNS1", "Japan1", "Korea1"}


@lru_cache(maxsize=8)
def load_standard_map(ordering, vertical):
    if ordering not in COLLECTIONS:
        raise ValueError(FONT_ERROR)
    from pdfminer.cmapdb import CMapDB

    return CMapDB.get_unicode_map("Adobe-" + ordering, vertical=vertical).cid2unichr


def unicode_stream(mapping, cids):
    entries = []
    for cid in cids:
        if cid == 0:
            continue  # .notdef has no semantic character.
        value = mapping.get(cid)
        if not isinstance(value, str) or not value or not 0 < cid <= 65535:
            raise ValueError(FONT_ERROR)
        entries.append(f"<{cid:04X}> <{value.encode('utf-16-be').hex().upper()}>")
    if not entries:
        raise ValueError(FONT_ERROR)
    lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<0000> <FFFF>",
        "endcodespacerange",
    ]
    for offset in range(0, len(entries), 100):
        batch = entries[offset : offset + 100]
        lines.extend([f"{len(batch)} beginbfchar", *batch, "endbfchar"])
    lines.extend(["endcmap", "end", "end"])
    stream = DecodedStreamObject()
    stream.set_data("\n".join(lines).encode("ascii"))
    return stream


class StandardCIDMapper:
    def __init__(self, reader):
        self.reader = reader
        self.repaired = {}
        self.text_forms = False

    @staticmethod
    def _actual_cids(values):
        cids = set()
        for value in values:
            if not isinstance(value, (str, bytes)) or not value:
                continue
            try:
                raw = value.original_bytes if isinstance(value, str) else bytes(value)
            except (AttributeError, UnicodeError) as exc:
                raise ValueError(FONT_ERROR) from exc
            if len(raw) % 2:
                raise ValueError(FONT_ERROR)
            cids.update(int.from_bytes(raw[i : i + 2], "big") for i in range(0, len(raw), 2))
        return cids

    def _font(self, font, values):
        font = font.get_object()
        identity = id(font)
        if identity in self.repaired:
            if not self._actual_cids(values) <= self.repaired[identity]:
                raise ValueError(FONT_ERROR)
            return True
        if (
            font.get("/Subtype") != "/Type0"
            or "/ToUnicode" in font
            or str(font.get("/Encoding")) not in {"/Identity-H", "/Identity-V"}
        ):
            return False
        try:
            child = font["/DescendantFonts"][0].get_object()
            info = child["/CIDSystemInfo"]
            ordering = str(info["/Ordering"])
            if str(info["/Registry"]) != "Adobe" or ordering not in COLLECTIONS:
                raise ValueError(FONT_ERROR)
            mapping = load_standard_map(ordering, str(font["/Encoding"]) == "/Identity-V")
            descriptor = child.get("/FontDescriptor")
            subset = descriptor.get_object().get("/CIDSet") if descriptor else None
            if subset is not None:
                bits = subset.get_object().get_data()
                if len(bits) > 8192:
                    raise ValueError(STRUCTURE_ERROR)
                cids = [
                    i * 8 + bit
                    for i, byte in enumerate(bits)
                    for bit in range(8)
                    if byte & (128 >> bit)
                ]
            else:
                cids = sorted(cid for cid in mapping if 0 < cid <= 65535)
            covered = {cid for cid in cids if cid != 0}
            if not self._actual_cids(values) <= covered:
                raise ValueError(FONT_ERROR)
            font[NameObject("/ToUnicode")] = unicode_stream(mapping, cids)
        except (ImportError, KeyError, IndexError, TypeError, AttributeError, UnicodeError) as exc:
            raise ValueError(FONT_ERROR) from exc
        self.repaired[identity] = covered
        return True

    def prepare_page(self, page):
        self.text_forms = False
        self._page_fonts = set()
        self._forms = 0
        self._operations = 0
        self._walk(page.get_contents(), page.get("/Resources", {}), None, set(), 0)
        return len(self._page_fonts)

    def _walk(self, content, resources, font, active, depth):
        if content is None:
            return
        if depth > 16:
            raise ValueError(STRUCTURE_ERROR)
        resources = resources.get_object() if hasattr(resources, "get_object") else resources
        stream = (
            content if isinstance(content, ContentStream) else ContentStream(content, self.reader)
        )
        if len(stream.get_data()) > 8 * 1024 * 1024:
            raise ValueError(STRUCTURE_ERROR)
        stack = []
        explicit_font = False
        for operands, operator in stream.operations:
            self._operations += 1
            if self._operations > 200000:
                raise ValueError(STRUCTURE_ERROR)
            if operator == b"q":
                if len(stack) >= 256:
                    raise ValueError(STRUCTURE_ERROR)
                stack.append((font, explicit_font))
            elif operator == b"Q":
                font, explicit_font = stack.pop() if stack else (None, False)
            elif operator == b"Tf":
                fonts = resources.get("/Font", {})
                fonts = fonts.get_object() if hasattr(fonts, "get_object") else fonts
                font = fonts.get(operands[0])
                explicit_font = True
            elif operator in {b"Tj", b"TJ", b"'", b'"'}:
                values = operands[0] if operator == b"TJ" else operands
                if not any(isinstance(v, (str, bytes)) and len(v) for v in values):
                    continue
                if font is None:
                    raise ValueError(FONT_ERROR)
                # pypdf's plain Form extractor does not inherit a parent's active
                # text font; do not silently return undecoded codes in that case.
                if depth and not explicit_font:
                    raise ValueError(FONT_ERROR)
                if self._font(font, values):
                    self._page_fonts.add(id(font.get_object()))
                self.text_forms |= depth > 0
            elif operator == b"Do":
                objects = resources.get("/XObject", {})
                objects = objects.get_object() if hasattr(objects, "get_object") else objects
                ref = objects.get(operands[0])
                if ref is None:
                    continue
                form = ref.get_object()
                if form.get("/Subtype") != "/Form":
                    continue
                self._forms += 1
                if self._forms > 256 or id(form) in active:
                    raise ValueError(STRUCTURE_ERROR)
                inherited = form.get("/Resources", resources)
                if "/Resources" not in form:
                    form[NameObject("/Resources")] = resources
                self._walk(form, inherited, font, active | {id(form)}, depth + 1)
