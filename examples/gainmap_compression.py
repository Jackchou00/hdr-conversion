import hdrconv.io as io


# Step 1: Read ISO 21496-1 Gainmap JPEG
print("Reading ISO 21496-1 file...")
gainmap_data = io.read_21496(
    "/Users/jackchou/Desktop/微信图片_20260325145857_1220_625.jpg"
)

print(f"  Baseline shape: {gainmap_data['baseline'].shape}")
print(f"  Gainmap shape: {gainmap_data['gainmap'].shape}")
print(f"  Metadata: {gainmap_data['metadata']}")

io.write_21496(
    data=gainmap_data,
    filepath="compressed_gainmap.jpg",
    gainmap_quality=60,
    baseline_quality=80,
)
