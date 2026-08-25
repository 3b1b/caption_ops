import re
from datetime import datetime, timedelta
import argparse

def parse_time(time_str):
    """Convert SRT timestamp to datetime object"""
    return datetime.strptime(time_str, '%H:%M:%S,%f')

def format_time(dt):
    """Convert datetime object back to SRT timestamp format"""
    return dt.strftime('%H:%M:%S,%f')[:-3]

def shift_timestamps(line, seconds):
    """Shift timestamps in a line by given number of seconds"""
    timestamp_pattern = r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})'
    match = re.match(timestamp_pattern, line)
    
    if match:
        start_time = parse_time(match.group(1))
        end_time = parse_time(match.group(2))
        
        # Apply the time shift
        shift = timedelta(seconds=seconds)
        new_start = start_time - shift
        new_end = end_time - shift
        
        # Ensure times don't go negative
        if new_start.day != 1 or new_end.day != 1:
            raise ValueError("Shift would result in negative timestamp")
        
        return f"{format_time(new_start)} --> {format_time(new_end)}"
    return line

def process_srt(input_file, output_file, shift_seconds):
    """Process the SRT file and shift all timestamps"""
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for line in lines:
                try:
                    shifted_line = shift_timestamps(line.strip(), shift_seconds)
                    f.write(f"{shifted_line}\n")
                except ValueError as e:
                    print(f"Warning: {e}")
                    f.write(line)
                    
        print(f"Successfully processed {input_file} and saved to {output_file}")
        
    except FileNotFoundError:
        print(f"Error: Could not find input file {input_file}")
    except Exception as e:
        print(f"Error: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Shift SRT subtitle timestamps')
    parser.add_argument('input_file', help='Input SRT file path')
    parser.add_argument('output_file', help='Output SRT file path')
    parser.add_argument('seconds', type=float, help='Number of seconds to shift back (positive number)')
    
    args = parser.parse_args()
    
    if args.seconds < 0:
        print("Please provide a positive number of seconds to shift back")
        return
    
    process_srt(args.input_file, args.output_file, args.seconds)

if __name__ == "__main__":
    main()