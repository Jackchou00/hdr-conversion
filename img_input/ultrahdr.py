import os
import numpy as np
from PIL import Image
import io
import xml.etree.ElementTree as ET
import cv2
import colour


def parse_gain_map_metadata(xmp_data):
    """
    Parses HDR Gain Map metadata from XMP (XML) data.

    Args:
        xmp_data (bytes): The XMP data, typically from an APP1 segment.

    Returns:
        dict: A dictionary containing the HDR Gain Map metadata, or an empty dict if not found.
    """
    try:
        # XMP data often starts with a namespace identifier, we need to find the start of the XML
        xml_content = xmp_data.decode("utf-8", errors="ignore")

        # Find the root element of the RDF description
        root = ET.fromstring(xml_content)

        # Define namespaces used in Ultra HDR metadata
        namespaces = {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "hdrgm": "http://ns.adobe.com/hdr-gain-map/1.0/",
        }

        # Find the rdf:Description tag
        description = root.find("rdf:RDF/rdf:Description", namespaces)

        if description is None:
            return {}

        metadata = {}

        # 1. Parse attributes of rdf:Description
        for key, value in description.attrib.items():
            if key.startswith("{" + namespaces["hdrgm"] + "}"):
                clean_key = key.replace("{" + namespaces["hdrgm"] + "}", "")
                try:
                    if "." in value:
                        metadata[clean_key] = float(value)
                    else:
                        metadata[clean_key] = int(value)
                except ValueError:
                    if value.lower() == "true":
                        metadata[clean_key] = True
                    elif value.lower() == "false":
                        metadata[clean_key] = False
                    else:
                        metadata[clean_key] = value

        # 2. Parse child elements of rdf:Description (e.g., GainMapMin, GainMapMax)
        for child in description:
            if child.tag.startswith("{" + namespaces["hdrgm"] + "}"):
                clean_key = child.tag.replace("{" + namespaces["hdrgm"] + "}", "")

                # Check for <rdf:Seq> which contains a list of values
                seq = child.find("rdf:Seq", namespaces)
                if seq is not None:
                    values = []
                    for li in seq.findall("rdf:li", namespaces):
                        if li.text:
                            try:
                                values.append(float(li.text.strip()))
                            except ValueError:
                                pass  # Ignore non-float values
                    if values:
                        metadata[clean_key] = values

        if metadata:
            return metadata

    except (ET.ParseError, UnicodeDecodeError, AttributeError):
        # Ignore errors if the segment is not valid XML or doesn't have the expected structure
        pass

    return {}


def extract_app_segments(jpeg_data):
    """
    Extract APP1 and APP2 segments from JPEG data.

    Args:
        jpeg_data (bytes): JPEG file data

    Returns:
        dict: Dictionary with 'APP1' and 'APP2' keys containing segment data
    """
    app_segments = {"APP1": [], "APP2": []}

    # APP1 marker: 0xFFE1, APP2 marker: 0xFFE2
    markers = {b"\xff\xe1": "APP1", b"\xff\xe2": "APP2"}

    offset = 0
    # Search within the header part of the JPEG, before Start of Scan (SOS) marker 0xFFDA
    sos_pos = jpeg_data.find(b"\xff\xda")
    search_limit = sos_pos if sos_pos != -1 else len(jpeg_data)

    for marker_bytes, segment_type in markers.items():
        offset = 0
        while True:
            # Only search in the JPEG header area
            pos = jpeg_data.find(marker_bytes, offset, search_limit)
            if pos == -1:
                break

            if pos + 4 <= len(jpeg_data):
                segment_length_bytes = jpeg_data[pos + 2 : pos + 4]
                segment_length = int.from_bytes(segment_length_bytes, byteorder="big")
                # The length includes the 2 bytes for the length field itself
                payload_start_pos = pos + 4
                payload_length = segment_length - 2

                if payload_length > 0 and payload_start_pos + payload_length <= len(
                    jpeg_data
                ):
                    payload_content = jpeg_data[
                        payload_start_pos : payload_start_pos + payload_length
                    ]
                    app_segments[segment_type].append(payload_content)

            offset = pos + len(marker_bytes)

    return app_segments


def extract_ultrahdr_data(
    input_file_path, save_to_files=False, output_dir="extracted_ultrahdr"
):
    """
    Extracts the primary image, gain map, and gain map metadata from an Ultra HDR JPEG.

    Args:
        input_file_path (str): Path to the Ultra HDR JPEG file.
        save_to_files (bool): Whether to save extracted components to files.
        output_dir (str): Output directory for saved files.

    Returns:
        dict: A dictionary containing 'primary_image' (numpy array),
              'gain_map' (numpy array), and 'gain_map_metadata' (dict).
              Returns an empty dictionary if it's not a valid Ultra HDR file.
    """
    with open(input_file_path, "rb") as f:
        data = f.read()

    # An Ultra HDR image contains two concatenated JPEG streams. The separator is
    # the EOI marker of the first (\xff\xd9) followed by the SOI marker of the
    # second (\xff\xd8).
    separator = b"\xff\xd9\xff\xd8"
    split_pos = data.find(separator)

    if split_pos == -1:
        print(
            "Could not find a valid Ultra HDR structure (marker between images not found)."
        )
        return {}

    # Split the data into two parts
    primary_jpeg_data = data[: split_pos + 2]
    gain_map_jpeg_data = data[split_pos + 2 :]

    # The gain map metadata is in the APP1 segment of the second image (the gain map)
    gain_map_metadata = {}
    app_segments = extract_app_segments(gain_map_jpeg_data)
    for i, segment_data in enumerate(app_segments.get("APP1", [])):
        # The actual XMP payload is after a null-terminated namespace string
        xmp_sig_pos = segment_data.find(b"\x00")
        if xmp_sig_pos != -1:
            xmp_payload = segment_data[xmp_sig_pos + 1 :]
            parsed_meta = parse_gain_map_metadata(xmp_payload)
            if parsed_meta:
                gain_map_metadata = parsed_meta
                break  # Found metadata, no need to check other segments

    if not gain_map_metadata:
        print(
            "Could not find a valid Ultra HDR structure (gain map metadata not found)."
        )
        return {}

    try:
        primary_image = np.array(Image.open(io.BytesIO(primary_jpeg_data)))
        gain_map = np.array(Image.open(io.BytesIO(gain_map_jpeg_data)))

        result = {
            "primary_image": primary_image,
            "gain_map": gain_map,
            "gain_map_metadata": gain_map_metadata,
        }

        if save_to_files:
            os.makedirs(output_dir, exist_ok=True)
            # Save Primary Image
            primary_filename = os.path.join(output_dir, "primary_image.jpg")
            with open(primary_filename, "wb") as f:
                f.write(primary_jpeg_data)

            # Save Gain Map
            gain_map_filename = os.path.join(output_dir, "gain_map.jpg")
            with open(gain_map_filename, "wb") as f:
                f.write(gain_map_jpeg_data)

            # Save Gain Map Metadata
            metadata_filename = os.path.join(output_dir, "gain_map_metadata.txt")
            with open(metadata_filename, "w", encoding="utf-8") as f:
                f.write("HDR Gain Map Metadata:\n")
                for key, value in gain_map_metadata.items():
                    f.write(f"  {key}: {value}\n")

        return result

    except (IOError, OSError) as e:
        print(f"Warning: Could not decode one of the JPEG streams. Error: {e}")
        return {}


def colour_convertion(major, gainmap, metadata):
    major_width = major.shape[1]
    major_height = major.shape[0]
    major = major / 255.0
    # major to linear
    major = colour.models.eotf_sRGB(major)
    gainmap = gainmap / 255.0
    gainmap = cv2.resize(gainmap, (major_width, major_height))

    # check the dim of gainmap (2D or 3D)
    if gainmap.ndim == 2:
        gainmap = np.stack([gainmap] * 3, axis=-1)  # Convert to 3-channel
    elif gainmap.ndim == 3 and gainmap.shape[2] == 1:
        gainmap = np.repeat(gainmap, 3, axis=2)

    # Use keys as they appear in XML, convert to numpy arrays for broadcasting
    gamma = np.array(metadata.get("Gamma", 1.0)).reshape(1, 1, -1)
    offset_sdr = np.array(metadata.get("OffsetSDR", 0.0)).reshape(1, 1, -1)
    offset_hdr = np.array(metadata.get("OffsetHDR", 0.0)).reshape(1, 1, -1)
    gainmap_min = np.array(metadata.get("GainMapMin", 0.0)).reshape(1, 1, -1)
    gainmap_max = np.array(metadata.get("GainMapMax", 1.0)).reshape(1, 1, -1)

    # Inverted Gainmap Gamma
    gainmap_degamma = gainmap ** (1 / gamma)

    gainmap_remapped = gainmap_degamma * (gainmap_max - gainmap_min) + gainmap_min
    gainmap_final = 2**gainmap_remapped

    hdr_image = gainmap_final * (major + offset_sdr) - offset_hdr
    return hdr_image


def read_uhdr(file_path, SDR_luminance=203.0):
    uhdr_data = extract_ultrahdr_data(file_path, save_to_files=False)
    if uhdr_data:
        primary_image = uhdr_data["primary_image"]
        gain_map = uhdr_data["gain_map"]
        gain_map_metadata = uhdr_data["gain_map_metadata"]

        hdr_image = colour_convertion(primary_image, gain_map, gain_map_metadata)

        # Scale HDR image to SDR luminance
        xyz_image = colour.RGB_to_XYZ(hdr_image, colourspace="Display P3")
        xyz_image = xyz_image * SDR_luminance / 10000

        # Convert from XYZ to Rec.2020 RGB
        rec2020_image = colour.XYZ_to_RGB(xyz_image, colourspace="ITU-R BT.2020")

        return rec2020_image


if __name__ == "__main__":
    # file_name = "Burger.jpg"
    file_name = "sample_image_gainmap.jpg"
    output_directory = "extracted_ultrahdr"

    ultrahdr_data = extract_ultrahdr_data(
        file_name, save_to_files=True, output_dir=output_directory
    )

    if ultrahdr_data:
        print("Successfully parsed Ultra HDR image.")
        print("-" * 30)
        print(f"Primary Image Shape: {ultrahdr_data['primary_image'].shape}")
        print(f"Primary Image Max: {np.max(ultrahdr_data['primary_image'])}")
        print(f"Gain Map Image Shape: {ultrahdr_data['gain_map'].shape}")
        print(f"Gain Map Image Max: {np.max(ultrahdr_data['gain_map'])}")
        print("-" * 30)
        print("HDR Gain Map Metadata:")
        for key, value in ultrahdr_data["gain_map_metadata"].items():
            print(f"  - {key}: {value}")

        print(f"\nExtracted files saved to '{output_directory}' directory.")

    hdr = colour_convertion(
        ultrahdr_data["primary_image"],
        ultrahdr_data["gain_map"],
        ultrahdr_data["gain_map_metadata"],
    )

    print(f"HDR Image Shape: {hdr.shape}")
    print(f"HDR Image Max: {np.max(hdr)}")
    print(f"HDR Image Min: {np.min(hdr)}")
