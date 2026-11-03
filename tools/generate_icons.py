"""Generate shared application icon assets from the source SVG brand mark."""
from pathlib import Path
import subprocess
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'branding'
OUT.mkdir(exist_ok=True)
SIZE = 1024
im = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.rounded_rectangle((18, 18, SIZE-18, SIZE-18), radius=235, fill='#174f43')
d.rounded_rectangle((28, 28, SIZE-28, SIZE-28), radius=225, outline='#276c5a', width=12)
# Shield, report sheet, and completion mark.
d.polygon([(512, 122), (818, 235), (818, 470), (785, 650), (684, 787), (512, 884), (340, 787), (239, 650), (206, 470), (206, 235)], outline='#e3eee7', fill=None, width=26)
d.rounded_rectangle((366, 320, 650, 700), radius=25, outline='#ffffff', width=24)
for y, right in [(405, 610), (485, 610), (565, 610)]:
    d.rounded_rectangle((412, y, right, y+18), radius=9, fill='#b9d8c7')
d.rounded_rectangle((412, 642, 535, 660), radius=9, fill='#b9d8c7')
d.line([(590, 286), (655, 350), (795, 200)], fill='#e7c775', width=34, joint='curve')
d.ellipse((574, 270, 606, 302), fill='#e7c775')

png = OUT / 'app-icon.png'
im.save(png)
# ICO contains common Windows sizes.
im.save(OUT / 'app-icon.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
if sys.platform == 'darwin':
    iconset = OUT / 'app-icon.iconset'
    iconset.mkdir(exist_ok=True)
    for base in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = base * scale
            suffix = f'@{scale}x' if scale == 2 else ''
            filename = f'icon_{base}x{base}{suffix}.png'
            im.resize((px, px), Image.Resampling.LANCZOS).save(iconset / filename)
    subprocess.run(['/usr/bin/iconutil', '-c', 'icns', str(iconset), '-o', str(OUT / 'app-icon.icns')], check=True)
print('Generated app-icon.png, app-icon.ico' + (', app-icon.icns' if sys.platform == 'darwin' else ''))
