"""Parser for Slovak e-kasa receipts via QR code extraction."""

import io
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

import cv2
import fitz  # PyMuPDF
import numpy as np
import requests
from PIL import Image


@dataclass
class EkasaReceipt:
    """Parsed e-kasa receipt data."""

    receipt_id: str
    total_price: Decimal
    issue_date: datetime
    vendor_name: str
    ico: str
    dic: Optional[str] = None
    items: list = None

    def __post_init__(self):
        if self.items is None:
            self.items = []


EKASA_API_URL = "https://ekasa.financnasprava.sk/mdu/api/v1/opd/receipt/find"

EKASA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko/20100101 Firefox/148.0",
    "Accept": "application/json",
    "Content-Type": "application/json;charset=utf-8",
    "Origin": "https://opd.financnasprava.sk",
    "Referer": "https://opd.financnasprava.sk/",
}


def extract_qr_from_pdf(pdf_path: Path) -> list[str]:
    """
    Extract QR codes from a PDF file.

    Uses OpenCV's QR detector which works better with scanned images.
    """
    qr_codes = []
    doc = fitz.open(pdf_path)
    detector = cv2.QRCodeDetector()

    for page in doc:
        # Try embedded images first
        for img_info in page.get_images():
            try:
                xref = img_info[0]
                pix = fitz.Pixmap(doc, xref)

                if pix.n > 4:  # CMYK
                    pix = fitz.Pixmap(fitz.csRGB, pix)

                # Convert to numpy array for OpenCV
                img_data = pix.tobytes("png")
                pil_image = Image.open(io.BytesIO(img_data))
                cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

                # Try original first (works better for high-res images)
                data, _, _ = detector.detectAndDecode(cv_image)
                if data:
                    qr_codes.append(data)
                else:
                    # Fall back to scaling for low-res images
                    for scale in [2, 3]:
                        scaled = cv2.resize(cv_image, None, fx=scale, fy=scale,
                                           interpolation=cv2.INTER_CUBIC)
                        data, _, _ = detector.detectAndDecode(scaled)
                        if data:
                            qr_codes.append(data)
                            break
            except Exception:
                continue

        # If no embedded images or no QR found, render the page
        if not qr_codes:
            for dpi in [200, 300]:
                pix = page.get_pixmap(dpi=dpi)
                img_data = pix.tobytes("png")
                pil_image = Image.open(io.BytesIO(img_data))
                cv_image = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)

                # Try original first (works better for high-res renders)
                data, _, _ = detector.detectAndDecode(cv_image)
                if data:
                    qr_codes.append(data)
                    break
                else:
                    # Scale up for low-res
                    scaled = cv2.resize(cv_image, None, fx=2, fy=2,
                                       interpolation=cv2.INTER_CUBIC)
                    data, _, _ = detector.detectAndDecode(scaled)
                    if data:
                        qr_codes.append(data)
                        break

    doc.close()
    return list(set(qr_codes))  # Deduplicate


def is_ekasa_receipt_id(data: str) -> bool:
    """Check if the QR data is an e-kasa receipt ID."""
    # E-kasa receipt IDs start with 'O-' followed by hex characters
    return bool(re.match(r'^O-[A-F0-9]{32}$', data))


def fetch_ekasa_receipt(receipt_id: str) -> Optional[EkasaReceipt]:
    """
    Fetch receipt details from the e-kasa API.

    Args:
        receipt_id: E-kasa receipt ID (format: O-XXXX...)

    Returns:
        EkasaReceipt if found, None otherwise
    """
    try:
        response = requests.post(
            EKASA_API_URL,
            headers=EKASA_HEADERS,
            json={"receiptId": receipt_id},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        if data.get("returnValue") != 0:
            return None

        receipt_data = data.get("receipt", {})
        org_data = receipt_data.get("organization", {})

        # Parse date - format: "21.02.2026 14:09:55"
        issue_date_str = receipt_data.get("issueDate", "")
        try:
            issue_date = datetime.strptime(issue_date_str, "%d.%m.%Y %H:%M:%S")
        except ValueError:
            issue_date = datetime.now()

        # Parse items
        items = []
        for item in receipt_data.get("items", []):
            items.append({
                "name": item.get("name", ""),
                "quantity": item.get("quantity", 1),
                "price": item.get("price", 0),
            })

        return EkasaReceipt(
            receipt_id=receipt_id,
            total_price=Decimal(str(receipt_data.get("totalPrice", 0))),
            issue_date=issue_date,
            vendor_name=org_data.get("name", ""),
            ico=receipt_data.get("ico", ""),
            dic=receipt_data.get("dic"),
            items=items,
        )

    except Exception as e:
        print(f"Error fetching e-kasa receipt: {e}")
        return None


def parse_ekasa_pdf(pdf_path: Path) -> Optional[EkasaReceipt]:
    """
    Parse an e-kasa receipt PDF by extracting QR code and fetching details.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        EkasaReceipt if successful, None otherwise
    """
    # Extract QR codes
    qr_codes = extract_qr_from_pdf(pdf_path)

    # Find e-kasa receipt ID
    for qr_data in qr_codes:
        if is_ekasa_receipt_id(qr_data):
            return fetch_ekasa_receipt(qr_data)

    return None
