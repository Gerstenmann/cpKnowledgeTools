"""First-party synthetic PDF bytes; no generator dependency or Golden input.

Only Helvetica ASCII, explicit coordinates and uncompressed streams are needed
to exercise the adapter contract. PDF xref offsets are calculated from bytes.
"""


def digital_pdf(
    pages=("The pilot is limited to 16 students.",),
    *,
    table=False,
    table_gap=False,
    image=False,
    title="Synthetic PDF",
) -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    page_refs = []
    for text in pages:
        page_id = len(objects) + 1
        page_refs.append(f"{page_id} 0 R")
        content_id = page_id + 1
        image_id = page_id + 2
        resource = f" /XObject << /Im1 {image_id} 0 R >>" if image else ""
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 3 0 R >>{resource} >> "
                f"/Contents {content_id} 0 R >>"
            ).encode()
        )
        lines = []
        for i, line in enumerate(text.splitlines()):
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            lines.append(f"BT /F1 12 Tf 50 {740 - i * 20} Td ({escaped}) Tj ET")
        if table:
            lines.extend(
                [
                    "50 500 m 250 500 l S",
                    "50 530 m 250 530 l S",
                    "50 560 m 250 560 l S",
                    "50 500 m 50 560 l S",
                    "150 500 m 150 560 l S",
                    "250 502 m 250 558 l S" if table_gap else "250 500 m 250 560 l S",
                    "BT /F1 12 Tf 60 540 Td (Team) Tj ET",
                    "BT /F1 12 Tf 160 540 Td (Count) Tj ET",
                    "BT /F1 12 Tf 60 510 Td (Blue) Tj ET",
                    "BT /F1 12 Tf 160 510 Td (16) Tj ET",
                ]
            )
        if image:
            lines.append("q 20 0 0 20 300 500 cm /Im1 Do Q")
        stream = "\n".join(lines).encode("ascii")
        objects.append(
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
        if image:
            objects.append(
                b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 "
                b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Length 3 >>"
                b"\nstream\n\xff\x00\x00\nendstream"
            )
    objects[1] = (
        f"<< /Type /Pages /Count {len(pages)} /Kids [{' '.join(page_refs)}] >>"
    ).encode()
    objects.append(f"<< /Title ({title}) /Author (Synthetic Author) >>".encode())
    output = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    output += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    return (
        output
        + (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R "
            f"/Info {len(objects)} 0 R >>\nstartxref\n{xref}\n%%EOF\n"
        ).encode()
    )
