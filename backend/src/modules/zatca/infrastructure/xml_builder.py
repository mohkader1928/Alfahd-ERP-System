"""UBL-lite invoice XML (FR-ZATCA-002).

Structurally modeled on ZATCA's UBL 2.1 e-invoice profile (element names,
nesting, the fields Sales actually has) but NOT validated against the real
ZATCA XSD/Schematron rules, and missing the `UBLExtensions` signature
envelope a real Cryptographic Stamp would occupy. Good enough to exercise
the full pipeline (canonicalize -> hash -> sign -> QR) with real, well-formed
XML; not schema-conformant for submission to the actual ZATCA platform.
"""

from xml.etree.ElementTree import Element, SubElement, tostring

from src.modules.zatca.domain.entities import InvoiceData

UBL_INVOICE_TYPE_CODES = {
    "tax": "388",
    "simplified": "388",
    "credit_note": "381",
    "debit_note": "383",
}


def build_invoice_xml(invoice: InvoiceData, *, uuid_value: str, icv: int) -> str:
    root = Element("Invoice", xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2")

    SubElement(root, "ID").text = invoice.invoice_number
    SubElement(root, "UUID").text = uuid_value
    SubElement(root, "IssueDateTime").text = invoice.issue_datetime_iso
    SubElement(root, "InvoiceTypeCode").text = UBL_INVOICE_TYPE_CODES[invoice.invoice_type]
    SubElement(root, "DocumentCurrencyCode").text = invoice.currency_code
    SubElement(root, "InvoiceCounterValue").text = str(icv)

    if invoice.original_invoice_number:
        billing_ref = SubElement(root, "BillingReference")
        SubElement(billing_ref, "InvoiceDocumentReference").text = invoice.original_invoice_number

    supplier = SubElement(root, "AccountingSupplierParty")
    SubElement(supplier, "RegistrationName").text = invoice.seller_name
    SubElement(supplier, "CompanyID").text = invoice.seller_vat_number

    if invoice.buyer_name:
        customer = SubElement(root, "AccountingCustomerParty")
        SubElement(customer, "RegistrationName").text = invoice.buyer_name
        if invoice.buyer_vat_number:
            SubElement(customer, "CompanyID").text = invoice.buyer_vat_number

    tax_total = SubElement(root, "TaxTotal")
    SubElement(tax_total, "TaxAmount", currencyID=invoice.currency_code).text = str(invoice.tax_amount)

    monetary_total = SubElement(root, "LegalMonetaryTotal")
    SubElement(monetary_total, "TaxExclusiveAmount", currencyID=invoice.currency_code).text = str(
        invoice.subtotal_amount
    )
    SubElement(monetary_total, "TaxInclusiveAmount", currencyID=invoice.currency_code).text = str(
        invoice.total_amount
    )
    SubElement(monetary_total, "PayableAmount", currencyID=invoice.currency_code).text = str(invoice.total_amount)

    for idx, line in enumerate(invoice.lines, start=1):
        invoice_line = SubElement(root, "InvoiceLine")
        SubElement(invoice_line, "ID").text = str(idx)
        SubElement(invoice_line, "InvoicedQuantity").text = str(line.quantity)
        SubElement(invoice_line, "LineExtensionAmount", currencyID=invoice.currency_code).text = str(
            line.line_total
        )
        item = SubElement(invoice_line, "Item")
        SubElement(item, "Description").text = line.description
        price = SubElement(invoice_line, "Price")
        SubElement(price, "PriceAmount", currencyID=invoice.currency_code).text = str(line.unit_price)
        line_tax = SubElement(invoice_line, "TaxTotal")
        SubElement(line_tax, "TaxAmount", currencyID=invoice.currency_code).text = str(line.tax_amount)
        SubElement(line_tax, "Percent").text = str(line.tax_rate_percent)

    return tostring(root, encoding="unicode")
