# First-party synthetic PDF fixtures

No real communications, Golden Truth or copied document is used. Ordinary
digital/image/table fixtures come from `tests/sources/pdf_fixture.py`, a small
first-party byte writer requiring no generator dependency.

The encrypted fixtures were generated on 2026-08-31 from `digital_pdf()` in an
isolated Python 3.14.6 environment using the reviewed pypdf 6.16.2 wheel:

```python
writer = pypdf.PdfWriter(clone_from=BytesIO(digital_pdf()))
writer.encrypt(user_password, owner_password="synthetic-owner", algorithm="RC4-128")
writer.write(output)
```

`encrypted.pdf` uses user password `synthetic-password`; the other fixture uses
an empty user password. These are public synthetic values, not credentials.
Both inputs must be rejected. pypdf is not a project runtime/test dependency.
Regenerated encryption IDs may vary; the committed bytes are stable test inputs.
