"""
Data viewer utility for exploring downloaded CSV files.
"""

import os
import pandas as pd
from pathlib import Path


OUTPUT_DIR = 'historical_data'


def list_available_files():
    """List all available CSV files."""
    if not os.path.exists(OUTPUT_DIR):
        print(f"❌ Directory not found: {OUTPUT_DIR}/")
        print("Run 'python extract_historical_data.py' first to download data.")
        return []

    files = sorted([f for f in os.listdir(OUTPUT_DIR) if f.endswith('.csv')])

    if not files:
        print(f"❌ No CSV files found in {OUTPUT_DIR}/")
        return []

    print("=" * 80)
    print("AVAILABLE DATA FILES")
    print("=" * 80)

    for i, filename in enumerate(files, 1):
        filepath = os.path.join(OUTPUT_DIR, filename)
        size = os.path.getsize(filepath)
        df = pd.read_csv(filepath)
        rows = len(df)

        print(f"{i:2}. {filename:35} | {rows:6,} rows | {size:10,} bytes")

    print("=" * 80)
    return files


def preview_file(filename, rows=10):
    """Preview a CSV file."""
    filepath = os.path.join(OUTPUT_DIR, filename)

    if not os.path.exists(filepath):
        print(f"❌ File not found: {filename}")
        return

    df = pd.read_csv(filepath)

    print("\n" + "=" * 80)
    print(f"FILE: {filename}")
    print("=" * 80)
    print(f"Rows: {len(df):,}")
    print(f"Columns: {', '.join(df.columns)}")

    if 'date' in df.columns:
        print(f"Date range: {df['date'].min()} to {df['date'].max()}")

    print(f"\nFirst {min(rows, len(df))} rows:")
    print("-" * 80)
    print(df.head(rows).to_string())

    print(f"\nLast {min(rows, len(df))} rows:")
    print("-" * 80)
    print(df.tail(rows).to_string())

    print("\n" + "=" * 80)


def show_summary():
    """Show summary of latest values from all indicators."""
    filepath = os.path.join(OUTPUT_DIR, '_summary_latest.csv')

    if not os.path.exists(filepath):
        print("❌ Summary file not found. Run extraction first.")
        return

    df = pd.read_csv(filepath)

    print("\n" + "=" * 80)
    print("LATEST VALUES SUMMARY")
    print("=" * 80)

    # Get most recent timestamp
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    latest_time = df['timestamp'].max()

    print(f"As of: {latest_time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    for _, row in df.iterrows():
        status = "✅" if row['status'] == 'success' else "❌"
        value = row.get('value_main', 'N/A')

        if pd.notna(value):
            print(f"{status} {row['indicator']:35} | {value:>12.2f}")
        else:
            print(f"{status} {row['indicator']:35} | {'N/A':>12}")

    print("=" * 80)


def interactive_viewer():
    """Interactive data viewer."""
    print("\n" + "=" * 80)
    print("MACRO INDICATORS - DATA VIEWER")
    print("=" * 80)

    while True:
        print("\nOptions:")
        print("  1. List all files")
        print("  2. View summary (latest values)")
        print("  3. Preview a file")
        print("  4. Export file info")
        print("  5. Exit")

        choice = input("\nEnter choice (1-5): ").strip()

        if choice == '1':
            list_available_files()

        elif choice == '2':
            show_summary()

        elif choice == '3':
            files = list_available_files()
            if files:
                file_num = input(f"\nEnter file number (1-{len(files)}): ").strip()
                try:
                    idx = int(file_num) - 1
                    if 0 <= idx < len(files):
                        preview_file(files[idx])
                    else:
                        print("❌ Invalid file number")
                except ValueError:
                    print("❌ Invalid input")

        elif choice == '4':
            export_file_info()

        elif choice == '5':
            print("\n👋 Goodbye!")
            break

        else:
            print("❌ Invalid choice")


def export_file_info():
    """Export information about all files to a text file."""
    output_file = 'data_files_info.txt'

    with open(output_file, 'w') as f:
        f.write("MACRO INDICATORS - DATA FILES INFORMATION\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.csv')]

        for filename in sorted(files):
            filepath = os.path.join(OUTPUT_DIR, filename)
            df = pd.read_csv(filepath)

            f.write(f"\nFILE: {filename}\n")
            f.write("-" * 80 + "\n")
            f.write(f"Rows: {len(df):,}\n")
            f.write(f"Columns: {', '.join(df.columns)}\n")

            if 'date' in df.columns:
                f.write(f"Date range: {df['date'].min()} to {df['date'].max()}\n")

            f.write("\n")

    print(f"✅ File info exported to: {output_file}")


def quick_stats(filename):
    """Show quick statistics for a file."""
    filepath = os.path.join(OUTPUT_DIR, filename)

    if not os.path.exists(filepath):
        print(f"❌ File not found: {filename}")
        return

    df = pd.read_csv(filepath)

    print("\n" + "=" * 80)
    print(f"STATISTICS: {filename}")
    print("=" * 80)

    numeric_cols = df.select_dtypes(include=['number']).columns

    for col in numeric_cols:
        print(f"\n{col}:")
        print(f"  Count:  {df[col].count():,}")
        print(f"  Mean:   {df[col].mean():.2f}")
        print(f"  Median: {df[col].median():.2f}")
        print(f"  Min:    {df[col].min():.2f}")
        print(f"  Max:    {df[col].max():.2f}")
        print(f"  Std:    {df[col].std():.2f}")

    print("=" * 80)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == 'list':
            list_available_files()
        elif command == 'summary':
            show_summary()
        elif command == 'preview' and len(sys.argv) > 2:
            preview_file(sys.argv[2])
        elif command == 'stats' and len(sys.argv) > 2:
            quick_stats(sys.argv[2])
        else:
            print("Usage:")
            print("  python view_data.py list              - List all files")
            print("  python view_data.py summary           - Show latest values")
            print("  python view_data.py preview <file>    - Preview a file")
            print("  python view_data.py stats <file>      - Show statistics")
            print("  python view_data.py                   - Interactive mode")
    else:
        interactive_viewer()
