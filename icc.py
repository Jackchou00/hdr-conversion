from PIL import Image


def extract_icc_profile(image_path, icc_output_path="Profile.icc"):
    """从图片中提取ICC配置文件"""
    with Image.open(image_path) as img:
        icc_profile = img.info.get("icc_profile")
        if icc_profile:
            with open(icc_output_path, "wb") as f:
                f.write(icc_profile)
            return True
    return False


def embed_icc_profile(image_path, icc_path, output_path, quality=95):
    """将ICC配置文件嵌入到图片中"""
    with open(icc_path, "rb") as f:
        icc_data = f.read()

    with Image.open(image_path) as img:
        img.save(output_path, quality=quality, icc_profile=icc_data)