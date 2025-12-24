"""Generate API reference pages dynamically."""

from pathlib import Path
import mkdocs_gen_files

nav = mkdocs_gen_files.Nav()

# Define the modules to document
modules = [
    ("core", "hdrconv.core"),
    ("convert", "hdrconv.convert"),
    ("io", "hdrconv.io"),
    ("identify", "hdrconv.identify"),
]

for path, module in modules:
    # Create the reference page
    with mkdocs_gen_files.open(f"api/{path}.md", "w") as f:
        f.write(f"::: {module}\n")

    # Add to navigation
    nav[path] = f"api/{path}.md"

# Write the navigation file
with mkdocs_gen_files.open("api/SUMMARY.md", "w") as f:
    f.write(str(nav))

# Create index page for API
with mkdocs_gen_files.open("api/index.md", "w") as f:
    f.write("""# API Reference

This section contains the complete API documentation for the hdrconv package.

## Module Overview

- **[Core Types](core.md)** - Data structures and type definitions
- **[Conversion Functions](convert.md)** - HDR format conversion algorithms
- **[I/O Operations](io.md)** - Reading and writing HDR formats
- **[Format Identification](identify.md)** - Format detection utilities

## Quick Usage

```python
# Import the package
import hdrconv

# Read an ISO 21496-1 file
data = hdrconv.io.read_21496("image.jxl")

# Convert to HDR
hdr = hdrconv.convert.gainmap_to_hdr(data)
```

For detailed usage examples, see the [Guides](../guides/getting-started.md) section.
""")