
import base64
import getpass
import json
from datetime import date

import requests


API_URL = "https://api.etimeoffice.com/api/DownloadPunchDataMCID"

EMPLOYEE_CODES = ["AT193", "AT119"]


def fetch_punch_data(
    corporate_id,
    username,
    password,
    employee_code,
    from_date,
    to_date,
):
    """
    Read-only eTimeOffice API request.
    Does not create or update ERPNext records.
    """

    credentials = f"{corporate_id}:{username}:{password}:true"
    encoded_credentials = base64.b64encode(
        credentials.encode("utf-8")
    ).decode("ascii")

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Accept": "application/json",
    }

    params = {
        "Empcode": employee_code,
        "FromDate": from_date,
        "ToDate": to_date,
    }

    response = requests.get(
        API_URL,
        headers=headers,
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"API ne valid JSON return kela nahi. HTTP {response.status_code}"
        ) from exc


def main():
    print("eTimeOffice READ-ONLY punch test")
    print("ERPNext records create/update honar nahit.\n")

    corporate_id = input("Corporate ID: ").strip()
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")

    today = date.today().strftime("%d/%m/%Y")
    from_date = (
        input(f"From date dd/mm/yyyy_HH:MM [{today}_00:00]: ").strip()
        or f"{today}_00:00"
    )
    to_date = (
        input(f"To date dd/mm/yyyy_HH:MM [{today}_23:59]: ").strip()
        or f"{today}_23:59"
    )

    for employee_code in EMPLOYEE_CODES:
        print(f"\n{'=' * 50}")
        print(f"Employee code: {employee_code}")
        print(f"Period: {from_date} to {to_date}")

        try:
            result = fetch_punch_data(
                corporate_id=corporate_id,
                username=username,
                password=password,
                employee_code=employee_code,
                from_date=from_date,
                to_date=to_date,
            )

            print(json.dumps(result, indent=2, ensure_ascii=False))

        except requests.RequestException as exc:
            print(f"API/network error for {employee_code}: {exc}")
        except Exception as exc:
            print(f"Error for {employee_code}: {exc}")


if __name__ == "__main__":
    main()
