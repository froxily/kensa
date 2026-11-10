import os
import sys


def main():
    directory = os.environ.get("TAMARIND_EXPORT_DIR")
    if not directory:
        sys.exit("TAMARIND_EXPORT_DIR is required")
    print(f"Export directory: {directory}")


if __name__ == "__main__":
    main()
