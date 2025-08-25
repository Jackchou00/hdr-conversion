"""
Read Jpeg file and explore its structure.

Not finished yet.

Target:

1. using binary search to find the markers (\xff\xd8 and \xff\xd9)
2. parse the APPn data from main and gainmap image.
3. Decode the gainmap data.
"""

from PIL import Image
import xml.etree.ElementTree as ET


# image_path = "Burger.jpg"
image_path = "sample_image_gainmap.jpg"

with Image.open(image_path) as img:
    for marker, content in img.app.items():
        print(f"Marker: {marker}, Content: {content[:10]}... (length: {len(content)})")

# Search the \xff\xd8 and \xff\xd9 markers
with open(image_path, "rb") as f:
    content = f.read()
    start_marker = b"\xff\xd8"
    start_positions = []
    pos = content.find(start_marker)