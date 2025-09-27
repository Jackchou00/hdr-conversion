# HDR Conversion 开发笔记

## 目标

解析和写入各种不同的图像格式，在它们之间做正确的颜色空间转换。

处理管线遵循以下流程：

文件 -> 原始组件 -> 规范化 HDR 图像 -> 目标组件 -> 文件

1.  解码 (Decoding): `FormatHandler` 读取物理文件，将其解析为格式特定的 `ImageContainer`（包含图像列表和元数据）。
2.  合成 (Composition): `Composer` 将 `ImageContainer` 中的原始组件合成为一个与格式无关的、规范化的线性 HDR 图像 (`IntermediateRendering`)。
3.  生成 (Generation): `Generator` 从规范化的 HDR 图像出发，根据目标格式的要求，生成对应的 `ImageContainer`（如 SDR 基础层+增益图）。
4.  编码 (Encoding): `FormatHandler` 将 `ImageContainer` 编码并写入到物理文件。

## 类

### `Image`

图像，从本质上来说是一个二维的数组，其中每个位置的数据称为像素值，像素值是定义在一个特定的坐标系中的，该坐标系称为颜色空间。

因此，定义一个类，存放图像数据，该类需有以下属性：

- content: numpy array，像素数据
- colorspace: `colour.RGB_Colourspace`，定义颜色空间
- image type: str/Enum 在 HDR 图像中，图像可能并不直接表示内容，也有可能是增益图，这个放的可能是 sdr/hdr/gainmap
  
### 颜色空间类

颜色空间由三基色坐标，白点坐标和传递函数定义，一般还会提供与 xyz 相互转换的方法。

直接使用 `colour-science` 中的类。

### `ImageContainer`

- `images`: List(Image)
- `metadata`: Dict
  
比如 UltraHDR 图片，`images`中有两个`Image`，`metadata`是 XMP 解析得到的 Dict。

### `IntermediateRendering` 

继承自 `Image`，颜色空间强制为一个规范化空间，比如 BT.2020 Linear

用于实现 `2n` 个转换过程，替代 `n(n-1)` 种直接转换。

## 格式处理器 (`hdr_converter/formats/`)

每个子模块负责一种文件格式的读写。

-    定义 `FormatHandler` 抽象基类 (`base.py`):
    -   `name` (property): 格式名称。
    -   `identify(stream: BinaryIO) -> bool`: 识别文件类型。
    -   `read(stream: BinaryIO) -> ImageContainer`: 从流中解码。
    -   `write(stream: BinaryIO, container: ImageContainer)`: 将 `ImageContainer` 编码到流。

-    实现 `UltraHDRHandler` (`ultrahdr.py`):
    -   实现 JPEG/MPF （多图格式） 的解析和写入。
    -   处理 XMP 元数据的读写。

-    实现 `ISO21496Handler` (`iso21496.py`):
    -   逻辑上可能与 `UltraHDRHandler` 非常相似，但遵循 ISO 标准。

-    实现 `SingleLayerPQHandler` （例如 HEIC/AVIF） (`heic_pq.py`):
    -   处理基于 HEVC/AV1 编码的单层 PQ 图像。

-    ... （未来可扩展其他格式）

## 内容解释器 (`hdr_converter/interpreters/`)

-    定义 `Composer` 抽象基类 (`composer_base.py`):
    -   `compose(container: ImageContainer) -> IntermediateRendering`: 合成规范化 HDR 图像。

-    定义 `Generator` 抽象基类 (`generator_base.py`):
    -   `generate(rendering: IntermediateRendering, options) -> ImageContainer`: 生成目标格式的组件。

-    实现 `GainmapComposer` 和 `GainmapGenerator` (`gainmap.py`):
    -   适用于 UltraHDR, ISO 21496, Apple Gainmap 等格式。
    -   `compose` 逻辑：应用增益图恢复线性 HDR。
    -   `generate` 逻辑：执行色调映射生成 SDR 基础层，并计算增益图。

-    实现 `SingleLayerComposer` 和 `SingleLayerGenerator` (`single_layer.py`):
    -   适用于单层 PQ/HLG 格式。
    -   `compose` 逻辑：解码传递函数（如 PQ），转换到线性空间。
    -   `generate` 逻辑：应用传递函数，从线性空间编码。

## 注册与调度 (`hdr_converter/`)

-    `registry.py`:
    -   维护一个所有 `FormatHandler` 实例的列表。
    -   提供一个工厂函数或字典，将格式名称映射到对应的 `Composer` 和 `Generator`。

-    `pipeline.py` / `converter.py`:
    -   实现高级转换函数 `convert(source_path, target_path, target_format)`。
    -   该函数将封装完整的 `解码 -> 合成 -> 生成 -> 编码` 流程。
