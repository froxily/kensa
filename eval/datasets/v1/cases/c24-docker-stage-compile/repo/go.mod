module lantern.invalid/agent

go 1.24

// This small agent has no external modules.
// The image compiles it in the build stage.
// The runtime stage contains only the binary.
// Module path is internal to this repository.
// Keep this file beside the Dockerfile.
// No generated files are required.
