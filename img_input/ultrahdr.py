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
        # A simple way is to find '<x:xmpmeta' or '<rdf:RDF'
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

        if description is not None:
            metadata = {}
            # Iterate through all attributes of the description tag
            for key, value in description.attrib.items():
                # Check if the attribute uses the hdrgm namespace
                if key.startswith("{" + namespaces["hdrgm"] + "}"):
                    # Clean up the key name (e.g., from '{...}GainMapMax' to 'GainMapMax')
                    clean_key = key.replace("{" + namespaces["hdrgm"] + "}", "")

                    # Try to convert values to float or int if possible
                    try:
                        if "." in value:
                            metadata[clean_key] = float(value)
                        else:
                            metadata[clean_key] = int(value)
                    except ValueError:
                        # Keep as string if conversion fails (e.g., "False")
                        if value.lower() == "true":
                            metadata[clean_key] = True
                        elif value.lower() == "false":
                            metadata[clean_key] = False
                        else:
                            metadata[clean_key] = value

            # Check if we actually extracted any hdrgm data
            if any(k.startswith("GainMap") for k in metadata.keys()):
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

    start_marker = b"\xff\xd8"
    end_marker = b"\xff\xd9"

    if save_to_files:
        os.makedirs(output_dir, exist_ok=True)

    # Store results for each found JPEG
    extracted_images = []
    gain_map_metadata = {}

    search_offset = 0

    while True:
        soi_pos = data.find(start_marker, search_offset)
        if soi_pos == -1:
            break

        eoi_pos = data.find(end_marker, soi_pos + 2)
        if eoi_pos == -1:
            # Handle cases where EOI might be missing, break loop
            break

        jpeg_data = data[soi_pos : eoi_pos + 2]

        try:
            image = Image.open(io.BytesIO(jpeg_data))
            image_array = np.array(image)

            # The gain map metadata is in the APP1 segment of the second image (gain map)
            # We will search all APP1 segments of all found jpegs for it.
            app_segments = extract_app_segments(jpeg_data)
            for segment_data in app_segments.get("APP1", []):
                # The actual XMP payload is after a null-terminated namespace string
                # e.g., b'http://ns.adobe.com/xap/1.0/\x00'
                xmp_sig_pos = segment_data.find(b"\x00")
                if xmp_sig_pos != -1:
                    xmp_payload = segment_data[xmp_sig_pos + 1 :]
                    parsed_meta = parse_gain_map_metadata(xmp_payload)
                    if parsed_meta:
                        # We found the gain map metadata, store it and the associated image
                        gain_map_metadata = parsed_meta

            extracted_images.append({"array": image_array, "data": jpeg_data})

        except (IOError, OSError) as e:
            print(f"Warning: Could not decode an embedded JPEG stream. Error: {e}")
            pass

        search_offset = eoi_pos + 2

    # According to Ultra HDR spec, there should be exactly two images.
    # The first is the primary SDR image, the second is the gain map.
    if len(extracted_images) >= 2 and gain_map_metadata:
        result = {
            "primary_image": extracted_images[0]["array"],
            "gain_map": extracted_images[1]["array"],
            "gain_map_metadata": gain_map_metadata,
        }

        if save_to_files:
            # Save Primary Image
            primary_filename = os.path.join(output_dir, "primary_image.jpg")
            with open(primary_filename, "wb") as f:
                f.write(extracted_images[0]["data"])

            # Save Gain Map
            gain_map_filename = os.path.join(output_dir, "gain_map.jpg")
            with open(gain_map_filename, "wb") as f:
                f.write(extracted_images[1]["data"])

            # Save Gain Map Metadata
            metadata_filename = os.path.join(output_dir, "gain_map_metadata.txt")
            with open(metadata_filename, "w", encoding="utf-8") as f:
                f.write("HDR Gain Map Metadata:\n")
                for key, value in gain_map_metadata.items():
                    f.write(f"  {key}: {value}\n")

        return result
    else:
        print(
            "Could not find a valid Ultra HDR structure (2 images and gain map metadata)."
        )
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

    gamma = metadata.get("gamma", 1.0)
    offset_sdr = metadata.get("OffsetSDR", 0.0)
    offset_hdr = metadata.get("OffsetHDR", 0.0)
    gainmap_min = metadata.get("GainMapMin", 0.0)
    gainmap_max = metadata.get("GainMapMax", 1.0)

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
        xyz_image = xyz_image * SDR_luminance

        return xyz_image


if __name__ == "__main__":
    file_name = "C:\\Users\\Jackc\\Desktop\\IMG20250623142451.jpg"
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
