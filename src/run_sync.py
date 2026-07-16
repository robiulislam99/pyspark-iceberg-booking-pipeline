"""
Mirrors sync_booking_properties.py management command.
Usage inside the container: python run_sync.py 20260716

BOOKING_DATA_DIR must be set as an env var -- file_locator/static_data read it internally now.
"""
import sys

from sync_iceberg import sync_accommodation_details

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run_sync.py <YYYYMMDD>")
        sys.exit(1)

    date_str = sys.argv[1]
    summary = sync_accommodation_details(date_str)
    print(summary)