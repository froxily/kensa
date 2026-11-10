# Operating Kiln

Build the container from the repository root.
Use a local image tag for development.
The application starts with Python.
The image uses the slim Python base.
Dependencies are installed during the build.
The source tree is copied into the image.
Review build output when a step fails.
Keep local tags distinct from release tags.
Rebuild after changing dependencies.
Run the container to check startup.
Use the workflow for repeatable builds.
