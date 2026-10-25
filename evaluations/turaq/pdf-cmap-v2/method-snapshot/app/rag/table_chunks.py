"""Heuristic table rows plus separate, literal source headers; never reconstructed quotes."""

import re

from .chunker import TextChunker

VERSION = "table-rows-v1"
_HEADER = re.compile(
    r"单位[：:]|币种|调整[前后]|\d{4}\s*年|第[一二三四]季度|^\s*(项目|主要会计数据|主要财务指标)"
)
_SECTION = re.compile(r"^\s*(?:[一二三四五六七八九十]+[、．.]|[（(][一二三四五六七八九十]+[）)])")


def table_units(text):
    """Return exact body/header slices. Fallback chunks preserve all narrative text."""
    lines = list(re.finditer(r"[^\n]*(?:\n|$)", text))
    lines = [line for line in lines if line.end() > line.start()]

    def data_line(line):
        body = line.group()
        numbers = list(TextChunker._numbers.finditer(body))
        # Period headings, dates and column names are not financial data rows.
        if _HEADER.search(body) or not re.search(r"[\u4e00-\u9fff]", body):
            return False
        return len(numbers) >= 2 or (len(numbers) == 1 and re.search(r"[%％]", body))

    indices = [i for i, line in enumerate(lines) if data_line(line)]

    def row_start(index):
        first = index
        while first > max(0, index - 3):
            previous = lines[first - 1].group()
            if (
                first >= 2
                and data_line(lines[first - 2])
                and re.search(r"(?:利润|净额|收益|资产|权益|润|额|产|流量)$", previous.strip())
            ):
                break
            if (
                not previous.strip()
                or len(re.sub(r"\s", "", previous)) > 24
                or TextChunker._numbers.search(previous)
                or _HEADER.search(previous)
                or _SECTION.search(previous)
            ):
                break
            first -= 1
        return first

    starts = {i: row_start(i) for i in indices}

    def part(start, end):
        return dict(text=text[start:end], char_start=start, char_end=end)

    units = []
    group_first = None
    group_header = []
    for pos, index in enumerate(indices):
        previous = indices[pos - 1] if pos else -1
        gap = "".join(line.group() for line in lines[previous + 1 : index])
        if (
            group_first is None
            or index - previous > 4
            or _HEADER.search(gap)
            or _SECTION.search(gap)
        ):
            group_first = index
            header_start_line = max(previous + 1, starts[index] - 8, 0)
            # The last unit marker starts a new table, not a continuation of the old header.
            markers = [
                i
                for i in range(header_start_line, starts[index])
                if re.search(r"单位[：:]", lines[i].group())
            ]
            if markers:
                header_start_line = markers[-1]
            begin = lines[header_start_line].start()
            end = lines[starts[index]].start()
            group_header = [part(max(begin, end - 800), end)] if end > begin else []
        next_start = starts[indices[pos + 1]] if pos + 1 < len(indices) else len(lines)
        end_line = index + 1
        while end_line < min(next_start, index + 4, len(lines)):
            following = lines[end_line].group()
            if (
                not following.strip()
                or _HEADER.search(following)
                or _SECTION.search(following)
                or len(re.sub(r"\s", "", following)) > 24
            ):
                break
            end_line += 1
        begin = lines[starts[index]].start()
        end = lines[end_line - 1].end()
        for chunk in TextChunker().chunk_with_metadata(text[begin:end]):
            body = part(begin + chunk["char_start"], begin + chunk["char_end"])
            units.append(
                dict(
                    kind="table_row",
                    body=body,
                    headers=list(group_header),
                    search_text="\n".join(p["text"] for p in [*group_header, body]),
                )
            )
    for chunk in TextChunker().chunk_with_metadata(text):
        body = part(chunk["char_start"], chunk["char_end"])
        units.append(dict(kind="text", body=body, headers=[], search_text=body["text"]))
    return units
