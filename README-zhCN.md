# HDR 格式转换工具

## 项目简介

本项目提供基于 Python 的 HDR 格式解析与写入研究，支持包括 UltraHDR、Adaptive Gainmap (ISO 21496-1) 以及纯 PQ/HLG 格式 (ISO 22028-5) 在内的多种格式的解析、写入和转换。

注意：仅用于研究与学习，不以生产可用性为目标。

## 功能

### 解析

对于 UltraHDR 和 Adaptive Gainmap 格式，支持结构化的提取以下内容：

- 主图像数据
- Gainmap 图像数据
- Gainmap 元数据

对于纯 PQ/HLG 格式，支持提取图像数据和相关元数据。

### 写入

将图像数据和结构化的元数据写入对应的格式中。

其中，UltraHDR 和 Adaptive Gainmap 格式通过手动编辑字节流与现有库提供的 JPEG 编码能力实现，而纯 PQ/HLG 格式则通过现有的库实现。

### 转换

根据元数据计算替代图像（Alternate Image），实现在 Gainmap 与纯 HDR 格式之间的转换。

## 参考标准

- [UltraHDR](https://developer.android.com/media/platform/hdr-image-format)：2025年4月发布的1.1版本
- [ISO 21496-1](https://www.iso.org/standard/86775.html)
- [ISO 22028-5](https://www.iso.org/standard/81863.html)

## 许可证

MIT，具体格式和依赖请参见各自的 LICENSE 文件。
