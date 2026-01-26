"""Generate API reference pages dynamically."""

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
