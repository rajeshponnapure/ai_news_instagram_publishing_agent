import urllib.request
from pathlib import Path

def download_fonts():
    fonts_dir = Path(__file__).resolve().parents[1] / "email_summary_agent" / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)

    font_urls = {
        "Roboto-Regular.ttf": "https://raw.githubusercontent.com/googlefonts/roboto/main/src/hinted/Roboto-Regular.ttf",
        "Roboto-Bold.ttf": "https://raw.githubusercontent.com/googlefonts/roboto/main/src/hinted/Roboto-Bold.ttf",
        "RobotoMono-Regular.ttf": "https://raw.githubusercontent.com/googlefonts/robotomono/main/fonts/ttf/RobotoMono-Regular.ttf"
    }

    for filename, url in font_urls.items():
        dest = fonts_dir / filename
        if dest.exists():
            print(f"{filename} already exists, skipping.")
            continue
        print(f"Downloading {filename} from {url}...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as response:
                dest.write_bytes(response.read())
            print(f"Successfully downloaded {filename}.")
        except Exception as e:
            print(f"Failed to download {filename}: {e}")

if __name__ == "__main__":
    download_fonts()
