"""
Usage:
    python -m orbital_watch.verify_imagery_cli \\
        --layers MODIS_Terra_Thermal_Anomalies_All,VIIRS_NOAA20_Thermal_Anomalies_375m_Day \\
        --date 2026-07-04
"""
from __future__ import annotations

import argparse
import sys

from orbital_watch.verify_imagery import verify_layer


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verify candidate NASA GIBS layer identifiers.")
    parser.add_argument("--layers", required=True, help="Comma-separated GIBS layer identifiers")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD to request")
    args = parser.parse_args(argv)

    all_valid = True
    for layer in args.layers.split(","):
        layer = layer.strip()
        check = verify_layer(layer, args.date)
        status = "VALID IMAGE" if check.is_valid_image else "NOT AN IMAGE"
        print(f"{layer}: {status} (HTTP {check.status_code}, {check.content_type}, {check.byte_count} bytes)")
        if not check.is_valid_image:
            all_valid = False
            print(f"  body preview: {check.body_preview}")

    return 0 if all_valid else 1


if __name__ == "__main__":
    sys.exit(main())
