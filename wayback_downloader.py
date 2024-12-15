import re, datetime, argparse, time, requests, os, json

class colors:
    CYAN = '\033[96m'
    WARNING = '\033[93m'
    ENDC = '\033[0m'

def logger(debug, message):
    if debug:
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"{colors.CYAN}[{colors.WARNING}debug{colors.CYAN}][{current_time}] {colors.ENDC}{message}")

def setup_argparse():
    parser = argparse.ArgumentParser(description="Robo Finder")
    parser.add_argument("--debug", action="store_true", default=False, help="Enable debugging mode.")
    parser.add_argument("--url", "-u", type=str, help="Base URL for archive search.")
    parser.add_argument("--retry", "-r", type=str, help="Path to status file for retrying failed downloads.")
    return parser.parse_args()

def construct_file_name(url):
    try:
        start = url.index("/web/") + 5
        end = url.index("if_/")
        timestamp = url[start:end]
        path = url[end + 4:].split('?', 1)[0]  # Remove query parameters
        file_name = os.path.basename(path)
        sanitized_file_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', file_name)  # Replace invalid characters
        return f"{timestamp}_{sanitized_file_name}"
    except ValueError:
        return None

def downloader(urls, debug, base_url):
    current_directory = os.getcwd()
    status = {"downloaded": [], "skipped": [], "errors": []}

    for url in urls:
        file_name = construct_file_name(url)
        if file_name:
            file_path = os.path.join(current_directory, file_name)
            if os.path.exists(file_path):
                logger(debug, f"File already exists, skipping download: {file_name}")
                status["skipped"].append(file_name)
                continue
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                with open(file_path, 'wb') as file:
                    file.write(response.content)
                logger(debug, f"Downloaded and saved: {file_name}")
                status["downloaded"].append(file_name)
            except requests.exceptions.RequestException as e:
                logger(debug, f"Failed to download {url}: {e}")
                status["errors"].append({"url": url, "error": str(e)})
        else:
            logger(debug, f"Could not construct a valid file name for URL: {url}")
            status["errors"].append({"url": url, "error": "Invalid file name"})

    create_status_file(status, base_url, debug)

def create_status_file(status, base_url, debug):
    sanitized_url = re.sub(r'[^a-zA-Z0-9_.-]', '_', base_url)
    status_file_name = f"status_{sanitized_url}.json"

    with open(status_file_name, 'w') as status_file:
        json.dump(status, status_file, indent=4)

    logger(debug, f"Status file created: {status_file_name}")

def get_all_links(url, debug):
    logger(debug, "Fetching archive links.")
    try:
        response = requests.get(f"https://web.archive.org/cdx/search/cdx?url={url}&output=json&fl=timestamp,original&filter=statuscode:200&collapse=digest")
        response.raise_for_status()
        obj = response.json()
    except Exception as e:
        logger(debug, f"Failed to fetch archive data: {e}")
        exit(1)

    url_list = [f"https://web.archive.org/web/{i[0]}if_/{i[1]}" for i in obj if len(i) > 1 and i != ["timestamp", "original"]]

    logger(debug, f"Found {len(url_list)} archive links.")
    if not url_list:
        logger(debug, "No valid files found in the archive. Exiting...")
        exit(1)

    return url_list

def retry_failed_downloads(status_file, debug):
    if not os.path.exists(status_file):
        logger(debug, f"Status file not found: {status_file}")
        exit(1)

    try:
        with open(status_file, 'r') as file:
            status_data = json.load(file)
    except json.JSONDecodeError as e:
        logger(debug, f"Failed to parse status file: {e}")
        exit(1)

    failed_urls = [item["url"] for item in status_data.get("errors", [])]

    if not failed_urls:
        logger(debug, "No failed downloads found in the status file.")
        return

    logger(debug, f"Retrying {len(failed_urls)} failed downloads.")
    
    for url in failed_urls:
        file_name = construct_file_name(url)
        if file_name:
            file_path = os.path.join(os.getcwd(), file_name)
            if os.path.exists(file_path):
                logger(debug, f"File already exists, skipping retry: {file_name}")
                continue
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                with open(file_path, 'wb') as file:
                    file.write(response.content)
                logger(debug, f"Downloaded and saved: {file_name}")
                status_data["downloaded"].append(file_name)
                # Remove retried URL from errors
                status_data["errors"] = [e for e in status_data["errors"] if e["url"] != url]
            except requests.exceptions.RequestException as e:
                logger(debug, f"Failed again to download {url}: {e}")
                # Update the error message in the status file
                for error_entry in status_data["errors"]:
                    if error_entry["url"] == url:
                        error_entry["error"] = str(e)

    # Save updated status file
    with open(status_file, 'w') as file:
        json.dump(status_data, file, indent=4)

    logger(debug, f"Updated status file: {status_file}")


def main():
    args = setup_argparse()
    start_time = time.time()
    logger(args.debug, "Program started.")

    if args.retry:
        retry_failed_downloads(args.retry, args.debug)
    elif args.url:
        url_list = get_all_links(args.url, args.debug)
        downloader(url_list, args.debug, args.url)
    else:
        logger(args.debug, "No valid input provided. Use --url or --retry.")

    logger(args.debug, f"Program completed in {time.time() - start_time:.2f} seconds.")

if __name__ == "__main__":
    main()
