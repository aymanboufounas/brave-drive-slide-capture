"""Capture complete PDF slides from the Google Drive preview in Brave."""

from __future__ import annotations

import argparse
import getpass
import io
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image
from fpdf import FPDF
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys


def brave_binary() -> Path:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware/Brave-Browser/Application/brave.exe",
        Path(r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"),
        Path(r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("Brave executable was not found")


def open_brave():
    options = Options()
    options.binary_location = str(brave_binary())
    profile = Path(os.environ["LOCALAPPDATA"]) / "BraveSoftware/Brave-Browser/User Data"
    options.add_argument(f"--user-data-dir={profile}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--start-maximized")
    return webdriver.Chrome(options=options)


def focused_page_input(driver):
    info = driver.execute_script("""
        const el = document.activeElement;
        if (!el || el.tagName !== 'INPUT') return null;
        return {id: el.id || '', aria: el.getAttribute('aria-label') || '',
                name: el.name || '', placeholder: el.placeholder || ''};
    """)
    if not info or not any(info.values()):
        raise RuntimeError("Could not identify the PDF page-number field. Click it and retry.")
    return info


def page_input(driver, info):
    element = driver.execute_script("""
        const info = arguments[0];
        const inputs = [...document.querySelectorAll('input')].filter(el => {
            const r = el.getBoundingClientRect(), s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && r.top >= 0 &&
                   r.top < innerHeight && s.visibility !== 'hidden';
        });
        const ranked = inputs.map(el => {
            let score = 0;
            if (info.id && el.id === info.id) score += 100;
            if (info.aria && el.getAttribute('aria-label') === info.aria) score += 80;
            if (info.name && el.name === info.name) score += 40;
            if (info.placeholder && el.placeholder === info.placeholder) score += 20;
            if (el.getBoundingClientRect().width < 120) score += 5;
            if ((el.parentElement?.parentElement?.innerText || '').includes('/')) score += 10;
            return {el, score};
        }).sort((a, b) => b.score - a.score);
        return ranked.length && ranked[0].score >= 15 ? ranked[0].el : null;
    """, info)
    if element is None:
        raise RuntimeError("PDF page-number field disappeared")
    return element


def navigate(driver, info, number: int, delay: float):
    field = page_input(driver, info)
    field.click()
    field.send_keys(Keys.CONTROL, "a")
    field.send_keys(str(number), Keys.ENTER)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        value = (page_input(driver, info).get_attribute("value") or "").strip()
        if value == str(number):
            time.sleep(delay)
            return
        time.sleep(0.2)
    raise RuntimeError(f"Viewer did not reach page {number}")


def _runs(values):
    positions = np.flatnonzero(values)
    if not len(positions):
        return []
    breaks = np.flatnonzero(np.diff(positions) > 1)
    starts = np.r_[0, breaks + 1]
    ends = np.r_[breaks, len(positions) - 1]
    return [(int(positions[a]), int(positions[b]) + 1) for a, b in zip(starts, ends)]


def detect_page(image: Image.Image):
    rgb = np.asarray(image.convert("RGB"))
    height, width, _ = rgb.shape
    background = np.median(rgb[int(height*.35):int(height*.7),
                               int(width*.93):int(width*.98)].reshape(-1, 3), axis=0)
    mask = np.max(np.abs(rgb.astype(np.int16) - background), axis=2) > 38
    y_start = int(height * .23)
    x_start, x_end = int(width*.50), int(width*.70)
    row_ratio = mask[y_start:, x_start:x_end].mean(axis=1)
    rows = [(a+y_start, b+y_start) for a,b in _runs(row_ratio > .75) if b-a > 100]
    if not rows:
        raise RuntimeError("Could not detect a full slide below the toolbar")
    top, bottom = rows[0]
    if bottom >= height-8:
        raise RuntimeError("Slide extends beyond the screen; reduce PDF zoom")
    mid_top = top + (bottom-top)//4
    mid_bottom = bottom - (bottom-top)//4
    x_start, x_end = int(width*.24), int(width*.90)
    column_ratio = mask[mid_top:mid_bottom, x_start:x_end].mean(axis=0)
    columns = [(a+x_start, b+x_start) for a,b in _runs(column_ratio > .75)
               if b-a > width*.22]
    if not columns:
        raise RuntimeError("Could not detect the slide's left and right edges")
    left, right = max(columns, key=lambda pair: pair[1]-pair[0])
    return (max(0,left-2), max(0,top-2), min(width,right+2), min(height,bottom+2))


def screenshot(driver):
    return Image.open(io.BytesIO(driver.get_screenshot_as_png())).convert("RGB")


def save_pdf(paths, destination: Path):
    if not paths:
        return
    pdf = FPDF(unit="mm")
    for path in paths:
        with Image.open(path) as img:
            width, height = img.size
        page_height = 297 * height / width
        pdf.add_page(format=(297, page_height))
        pdf.image(str(path), x=0, y=0, w=297, h=page_height)
    pdf.output(str(destination))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder-url", required=True, help="Google Drive folder URL")
    parser.add_argument("--pages", type=int, required=True, help="Number of PDF pages")
    parser.add_argument("--output", type=Path, default=Path.home()/"Desktop"/"Slides")
    parser.add_argument("--delay", type=float, default=2.5, help="Seconds to wait after each page change")
    args = parser.parse_args()
    if args.pages < 1 or args.delay < 0:
        parser.error("--pages must be positive and --delay nonnegative")
    args.output.mkdir(parents=True, exist_ok=True)
    images = args.output / "slide_screenshots"
    images.mkdir(exist_ok=True)

    driver = None
    paths = []
    try:
        driver = open_brave()
        driver.get(args.folder_url)
        print("Open the PDF, show its entire first page, close popups, then click its page-number field.")
        input("Return to this terminal and press Enter: ")
        info = focused_page_input(driver)
        navigate(driver, info, 1, args.delay)
        first = screenshot(driver)
        crop = detect_page(first)
        print(f"Detected slide rectangle: {crop}")
        for number in range(1, args.pages+1):
            navigate(driver, info, number, args.delay)
            full = screenshot(driver)
            if crop[2] > full.width or crop[3] > full.height:
                raise RuntimeError("Browser dimensions changed during capture")
            path = images / f"slide_{number:03d}.png"
            full.crop(crop).save(path)
            paths.append(path)
            print(f"Captured {number}/{args.pages}")
        middle = (len(paths)+1)//2
        save_pdf(paths[:middle], args.output/"Slides_Part1.pdf")
        save_pdf(paths[middle:], args.output/"Slides_Part2.pdf")
        print(f"Finished. Files are in {args.output}")
    finally:
        if driver:
            driver.quit()
        if paths and len(paths) < args.pages:
            print(f"Kept {len(paths)} screenshots in {images}")


if __name__ == "__main__":
    main()
