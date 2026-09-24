# Brave Drive Slide Capture

Capture each visible slide from a Google Drive PDF preview in Brave, save PNG screenshots, and assemble two PDF files. The script uses your existing Brave `Default` profile, so you can open a PDF that requires your Google account.

## Requirements

- Windows 10/11, Python 3.10+
- Brave Browser and an existing `Default` profile
- A PDF that you are authorized to view and capture

Install dependencies:

```powershell
py -m pip install -r requirements.txt
```

## Run

```powershell
py main.py --folder-url "https://drive.google.com/drive/folders/YOUR_FOLDER_ID" --pages 225 --output "C:\Users\YOUR_NAME\Desktop\Slides"
```

1. Close Brave before running, so its profile is available.
2. In the Brave window opened by the script, open the PDF and go to page 1.
3. Adjust the PDF viewer zoom until one **entire slide** fits on screen. Close popups and click the page-number field showing `1`.
4. Return to PowerShell and press Enter. The program navigates by page number and captures the slide automatically. Do not resize the window or change zoom while it runs.

PNG files are written to `slide_screenshots`. Two PDFs are written to the output directory. On an error, existing PNGs remain so you can inspect them. The script does not delete previous screenshots automatically; it overwrites pages as they are captured.

## How it works

The program finds the largest PDF page below Drive's toolbar from the first browser screenshot, then applies that crop to every page. It checks the page-number field before saving. This screen-based approach depends on the viewer layout, theme, and slides: inspect the first few output PNGs before relying on a full run. Slides with nearly the same color as the dark viewer background or a changed viewer layout may require a code adjustment. It does not download the original PDF.

## Troubleshooting

- **`DevToolsActivePort file doesn't exist`**: close all Brave processes before running. The existing `Default` profile cannot be opened by two Brave instances at once.
- **`Could not identify the PDF page-number field`**: make sure you clicked the small page field in the PDF toolbar, not Drive search.
- **Incomplete slide**: reduce the PDF zoom so the whole page fits above the bottom edge; keep Brave maximized.
- **`Could not detect a full slide`**: try a different first page with a clear edge against the viewer background, or use the original PDF instead of browser screenshots.

This project is an experimental screen capture utility. It does not bypass Google Drive access permissions or download restrictions.
