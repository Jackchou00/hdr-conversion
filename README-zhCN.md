# HDR 格式转换工具

## 项目简介

高动态范围（HDR）成像技术在现代摄影领域日益普及。本项目提供基于 Python 的 HDR 格式转换解决方案，支持包括 UltraHDR、Gainmap (ISO 21496-1) 以及纯 PQ/HLG 格式 (ISO 22028-5) 在内的多种格式互转。

## 架构概述

转换流程采用线性光色彩空间作为中间转换枢纽，首先将源格式转换为线性光表示，随后再转换为目标格式。

## 参考标准

- [UltraHDR](https://developer.android.com/media/platform/hdr-image-format)：2025年4月发布的1.1版本
- [ISO 21496-1](https://www.iso.org/standard/86775.html)
- [ISO 22028-5](https://www.iso.org/standard/81863.html)

## 依赖项

- `colour-science`：负责传输函数和色彩空间转换
- `libultrahdr`：提供 UltraHDR 格式支持（元数据读取和完整写入功能）
- `pillow-heif`：实现 AVIF 格式的读写操作

## 开发规划

- 开发完整的 HDR 格式识别系统
- 改进 Gainmap 读取器，替代当前简易的 `FF D9 FF D8` 模式匹配方案
- 从 `pillow_heif` 迁移至标准 `pillow` 库以实现 AVIF 支持
- 将 Apple HEIC 格式集成到现有的输入输出方式中。
